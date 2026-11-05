"""Owner-scoped learning dashboards and planning over deterministic projections."""

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.principals import owner_ids, root_owner_id
from app.content import ContentBundle
from app.errors import ApiError
from app.instances import instance_key, recent_exposure
from app.learning.annotations import (
    annotation_view,
    annotations_for,
    journal_and_favourites,
    mutation,
    save_annotation,
)
from app.learning.evidence import (
    History,
    editorial_exclusions,
    editorial_notices,
    load_history,
    owned_task,
    persist_history,
)
from app.learning.models import LearningState
from app.learning.planning import estimate_seconds, plan_length
from app.learning.policy import (
    DEFAULT_POLICY,
    LearningPolicy,
    LearningProjection,
    canonical_evidence,
    replay,
    slot_progress,
)
from app.learning.schemas import (
    AnnotationRequest,
    Dashboard,
    ExportReview,
    LearningExport,
    Notification,
    Pagination,
    Plan,
    ReviewView,
    SkillProgress,
    SlotProgress,
    WeakSkill,
)
from app.learning.selection import mixed_candidates
from app.models import Guest
from app.schemas import CreateSessionRequest
from app.services import LearningService, StoredResponse


class LearningExtrasService:
    def __init__(
        self, learning_service: LearningService, policy: LearningPolicy = DEFAULT_POLICY,
    ) -> None:
        self.learning = learning_service
        self.policy = policy

    def _version_notice(
        self, db: Session, guest: Guest, now: datetime, *, persist: bool,
    ) -> str | None:
        root = root_owner_id(db, guest.id)
        state = db.get(LearningState, root)
        config = json.loads(json.dumps(asdict(self.policy)))
        # Newly claimed origins may predate a policy already used by the root.
        previous = list(db.scalars(
            select(LearningState).where(LearningState.owner_id.in_(owner_ids(db, guest))),
        ))
        if any(item.algorithm_version == self.policy.version and item.policy_config != config
               for item in previous):
            raise ApiError(
                503, "policy_version_conflict",
                "Изменение порогов требует новой версии алгоритма.",
            )
        current_notice = (
            state.notice if state is not None and state.algorithm_version == self.policy.version
            else None
        )
        # A root upgrade removes its old version from the rows, not from its explanation.
        explained = {
            version
            for group in re.findall(
                rf"Алгоритм обновлён: (.*?) → {re.escape(self.policy.version)}\. ",
                current_notice or "",
            )
            for version in group.split(", ")
        }
        versions = sorted({item.algorithm_version for item in previous
                           if item.algorithm_version != self.policy.version} - explained)
        notice = (
            f"Алгоритм обновлён: {', '.join(versions)} → {self.policy.version}. "
            "Освоение и повторения пересчитаны по новым порогам; исходная история сохранена."
            if versions else None
        )
        if state is not None and state.algorithm_version == self.policy.version:
            if notice is None:
                return state.notice
            notice = f"{state.notice} {notice}" if state.notice else notice
        if persist:
            if state is None:
                db.add(LearningState(
                    owner_id=root, algorithm_version=self.policy.version, policy_config=config,
                    notice=notice, updated_at=now,
                ))
            else:
                state.algorithm_version = self.policy.version
                state.policy_config = config
                state.notice = notice
                state.updated_at = now
        return notice

    def dashboard(self, token: str | None, *, limit: int = 50, offset: int = 0) -> Dashboard:
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            bundle = self.learning.content(db)
            guest = self.learning.reauthorize(db, token)
            return self.dashboard_for(db, guest, bundle, limit=limit, offset=offset, persist=True)

    def annotate(
        self, token: str | None, request: AnnotationRequest, key: str | None,
    ) -> StoredResponse:
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            context = owned_task(db, owner_ids(db, guest), request.session_id, request.task_id)
            return self.learning._idempotent(
                db, guest, key, "POST /learning/annotations", mutation(request),
                lambda: save_annotation(db, context, request, self.learning.clock()),
            )

    def plan(self, token: str | None, minutes: int) -> Plan:
        if minutes not in {10, 20, 30}:
            raise ApiError(422, "invalid_minutes", "Выберите 10, 20 или 30 минут.")
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            bundle = self.learning.content(db)
            guest = self.learning.reauthorize(db, token)
            now = self.learning.clock()
            owners = owner_ids(db, guest)
            history = load_history(db, owners, practice=self.learning._history(db, guest))
            persist_history(db, owners, history, now)
            version_notice = self._version_notice(db, guest, now, persist=True)
            excluded = editorial_exclusions(db)
            projection = replay(history.events, self.policy, exclusions=excluded)
            exposure = recent_exposure(
                db, owners, bundle.tasks, now, days=self.policy.instance_exclusion_days,
            )
            permitted = ContentBundle(bundle.profile, bundle.lessons, tuple(
                task for task in bundle.available_tasks(
                    allow_demo_content=self.learning.settings.allow_demo_content,
                ) if (task.id, task.revision) not in excluded
                and task.id not in exposure.ids and instance_key(task) not in exposure.keys
            ))
            length = plan_length(minutes, permitted.tasks, projection)
            slots = [slot.number for slot in bundle.profile.slots]
            request = CreateSessionRequest(
                slots=slots, length=length, mode="practice", selection="mixed",
            )
            selected = mixed_candidates(
                permitted, request, projection, {}, now,
                f"plan:{now.date().isoformat()}:{minutes}", owner_id=root_owner_id(db, guest.id),
                instance_aware=True,
            )
            notices = [part for part in (version_notice, selected.notice) if part]
            notices.append(
                "Время — ориентир: закончите текущую задачу и затем решите, продолжать ли.",
            )
            return Plan(
                minutes=minutes, length=length,
                estimated_seconds=estimate_seconds(selected.tasks, projection),
                slots=slots, selection="mixed", notice=" ".join(notices),
            )

    def export(self, token: str | None, *, limit: int = 50, offset: int = 0) -> LearningExport:
        if not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
            raise ApiError(422, "invalid_page", "Проверьте размер и начало страницы.")
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            now = self.learning.clock()
            owners = owner_ids(db, guest)
            history = load_history(db, owners, practice=self.learning._history(db, guest))
            persist_history(db, owners, history, now)
            self._version_notice(db, guest, now, persist=True)
            projection = replay(history.events, self.policy, exclusions=editorial_exclusions(db))
            annotations = list(annotations_for(db, owners, history).values())
            reviews = [ExportReview(
                skill_id=item.skill_id, family_id=item.family_id, slot_id=item.slot_id,
                due_at=item.due_at.isoformat() if item.due_at else None,
                interval_days=item.interval_days, closed=item.due_at is None,
                anchor_task_id=item.anchor_task_id, anchor_at=item.anchor_at.isoformat(),
            ) for item in projection.reviews]
            return LearningExport(
                version="1", algorithm_version=self.policy.version, exported_at=now.isoformat(),
                annotations=[annotation_view(row) for row in annotations[offset:offset + limit]],
                reviews=reviews[offset:offset + limit],
                pagination=Pagination(offset=offset, limit=limit, totals={
                    "annotations": len(annotations), "reviews": len(reviews),
                }),
            )

    def dashboard_for(
        self, db: Session, guest: Guest, bundle: ContentBundle, *, now: datetime | None = None,
        limit: int = 50, offset: int = 0, persist: bool = False,
    ) -> Dashboard:
        """Use an existing authenticated transaction; never load content or open a DB here."""
        if not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
            raise ApiError(422, "invalid_page", "Проверьте размер и начало страницы.")
        now = now or self.learning.clock()
        owners = owner_ids(db, guest)
        history = load_history(db, owners, practice=self.learning._history(db, guest))
        if persist:
            persist_history(db, owners, history, now)
        version_notice = self._version_notice(db, guest, now, persist=persist)
        exclusions = editorial_exclusions(db)
        projection = replay(history.events, self.policy, exclusions=exclusions)
        slots = self._slots(bundle, projection)
        reviews = self._reviews(bundle, projection, now)
        weak = self._weak_skills(bundle, projection)
        annotations = annotations_for(db, owners, history)
        journal, favourites = journal_and_favourites(history, annotations)
        affected = {(item.task_id, item.task_revision): item.at for item in history.events
                    if (item.task_id, item.task_revision) in exclusions}
        notices = {(item["task_id"], item["task_revision"]): item
                   for item in editorial_notices(db, owners)
                   if (item["task_id"], item["task_revision"]) in affected}
        notifications = [Notification(
            id=notices.get((task_id, revision), {}).get("id", f"excluded:{task_id}:{revision}"),
            message=f"Результат задачи {task_id} (ред. {revision}) исключён: "
                    f"{exclusions[(task_id, revision)]}",
            created_at=notices.get((task_id, revision), {}).get("created_at", at.isoformat()),
        ) for (task_id, revision), at in sorted(affected.items())]
        notifications.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        notice_parts = [version_notice] if version_notice else []
        if affected:
            notice_parts.append(
                f"Из расчёта исключены ошибочные редакции: {len(affected)}. "
                "Причины указаны в уведомлениях; история ответов сохранена."
            )
        visible = {item.id for item in projection.evidence}
        attempts = [item for identifier, item in history.attempts.items() if identifier in visible]
        arrays = {
            "reviews": reviews, "weak_skills": weak, "favourites": favourites, "journal": journal,
            "assessment_history": history.assessments, "notifications": notifications,
        }
        recommendation = (
            "Начните с повторения по сроку, затем переходите к слабым навыкам."
            if any(item.due_at is not None and item.due_at <= now for item in projection.reviews)
            else f"Повторите навык «{weak[0].title}» и проверьте себя на другой задаче."
            if weak else "Продолжите смешанную практику на новых семействах задач."
        )
        return Dashboard(
            algorithm_version=self.policy.version, notice=" ".join(notice_parts) or None,
            independent_total=sum(item.independent for item in projection.evidence),
            independent_correct=sum(item.independent and item.correct
                                    for item in projection.evidence),
            assisted_total=sum(item.assisted and not item.skipped for item in attempts),
            corrections_total=self._corrections_total(history, visible),
            skipped_total=len({
                (history.event_tasks[identifier].session_id, item.task_id)
                for identifier, item in history.attempts.items()
                if identifier in visible and item.skipped
            }),
            excluded_total=len(projection.excluded_ids), slots=slots,
            **{name: values[offset:offset + limit] for name, values in arrays.items()},
            recommendation=recommendation,
            pagination=Pagination(offset=offset, limit=limit,
                                  totals={name: len(values) for name, values in arrays.items()}),
        )

    @staticmethod
    def _corrections_total(history: History, visible: set[str]) -> int:
        """Count visible numeric repeats across the canonical owner's full history."""
        seen: set[str] = set()
        total = 0
        for event in canonical_evidence(history.events):
            attempt = history.attempts.get(event.id)
            if attempt is None or attempt.skipped or attempt.normalized_answer is None:
                continue
            instance = event.instance_id or event.task_id
            if instance in seen and event.id in visible:
                total += 1
            # An excluded numeric result still precedes later answers on this instance.
            seen.add(instance)
        return total

    @staticmethod
    def _slots(bundle: ContentBundle, projection: LearningProjection) -> list[SlotProgress]:
        result = []
        for slot in bundle.profile.slots:
            progress = slot_progress(projection, slot.id, (skill.id for skill in slot.skills))
            skills = []
            for skill in slot.skills:
                attempts = [item for item in projection.evidence
                            if item.independent and skill.id in item.skill_ids]
                skills.append(SkillProgress(
                    id=skill.id, title=skill.title, attempts=len(attempts),
                    correct=sum(item.correct for item in attempts),
                ))
            result.append(SlotProgress(
                slot_id=slot.id, number=slot.number, title=slot.title, status=progress.status,
                attempts=progress.attempts, correct=progress.correct,
                covered_skills=progress.covered_skills, total_skills=progress.total_skills,
                skills=skills,
            ))
        return result

    @staticmethod
    def _reviews(
        bundle: ContentBundle, projection: LearningProjection, now: datetime,
    ) -> list[ReviewView]:
        numbers = {slot.id: slot.number for slot in bundle.profile.slots}
        active = sorted((item for item in projection.reviews if item.due_at is not None),
                        key=lambda item: (item.due_at, item.skill_id, item.family_id))
        return [ReviewView(
            skill_id=item.skill_id, family_id=item.family_id, slot_id=item.slot_id,
            slot=numbers.get(item.slot_id), due_at=item.due_at.isoformat(),
            interval_days=item.interval_days, overdue=item.due_at < now,
        ) for item in active]

    def _weak_skills(
        self, bundle: ContentBundle, projection: LearningProjection,
    ) -> list[WeakSkill]:
        ranked = []
        for slot in bundle.profile.slots:
            for skill in slot.skills:
                attempts = [item for item in projection.evidence
                            if item.independent and skill.id in item.skill_ids]
                recent = attempts[-self.policy.recent_window:]
                accuracy = Fraction(sum(item.correct for item in recent), len(recent) or 1)
                covered = any(item.correct for item in attempts)
                if (
                    covered and len(recent) >= self.policy.recent_window
                    and accuracy >= Fraction(self.policy.recent_correct, self.policy.recent_window)
                ):
                    continue
                latest = attempts[-1].at if attempts else datetime.min.replace(tzinfo=UTC)
                families = sorted({task.family_id for task in bundle.tasks
                                   if skill.id in task.skill_ids})
                ranked.append(((covered, accuracy, latest, skill.id), WeakSkill(
                    id=skill.id, title=skill.title, slot=slot.number, family_ids=families,
                )))
        return [item for _, item in sorted(ranked, key=lambda pair: pair[0])]
