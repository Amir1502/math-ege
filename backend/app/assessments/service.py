"""Owner-serialized assessment preparation and lifecycle."""

import hashlib
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.principals import root_owner_id
from app.assessments.grading import build_result, complete_snapshot, content_hash
from app.assessments.models import AssessmentRecord
from app.assessments.presentation import assessment_view
from app.assessments.schemas import (
    AssessmentView,
    DraftAnswer,
    DraftRequest,
    FinishRequest,
    PrepareRequest,
    WriterRequest,
)
from app.checker import AnswerFormatError, parse_answer
from app.eligibility import prior_numeric_ids
from app.errors import ApiError, not_found
from app.instances import aliases_for_task, instance_key, mark_instances, recent_exposure
from app.issuance import generate_candidates
from app.models import Guest, SeenTask
from app.schemas import CreateSessionRequest
from app.services import LearningService, StoredResponse, json_text, request_uuid


class AssessmentService:
    def __init__(self, learning_service: LearningService) -> None:
        self.learning = learning_service

    def _owned(self, db: Session, guest: Guest, assessment_id: str) -> AssessmentRecord:
        record = db.scalar(select(AssessmentRecord).where(
            AssessmentRecord.id == assessment_id,
            AssessmentRecord.guest_id.in_(self.learning.owner_ids(db, guest)),
        ).with_for_update())
        if record is None:
            raise not_found()
        return record

    @staticmethod
    def _writer(record: AssessmentRecord, request: WriterRequest) -> None:
        if (str(request.device_id) != record.writer_device_id
                or request.writer_generation != record.writer_generation):
            raise ApiError(
                409, "assessment_writer_conflict",
                "Управление принадлежит другому устройству или поколению. Обновите сессию.",
            )

    def _mutate(
        self, token: str | None, assessment_id: str, request: WriterRequest,
        key: str | None, operation: str,
        action: Callable[[Session, Guest, AssessmentRecord, datetime], AssessmentView],
    ) -> StoredResponse:
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            record = self._owned(db, guest, assessment_id)
            guest = self.learning.reauthorize(db, token)
            # One acceptance instant after both locks: crossing the deadline
            # during serialization must not produce an inconsistent snapshot.
            now = self.learning.clock()
            self._freeze_due(db, guest, record, now)
            try:
                response = self.learning._idempotent(
                    db, guest, key, f"POST /assessments/{record.id}/{operation}", request,
                    lambda: action(db, guest, record, now),
                )
            except ApiError as exc:
                if exc.status_code == 401:
                    raise
                response = StoredResponse(exc.status_code, json_text(exc.response()))
        return response

    def get(
        self, token: str | None, assessment_id: str, device_id: str | None = None
    ) -> AssessmentView:
        with self.learning._guest_transaction(token, write=True) as (db, guest):
            record = self._owned(db, guest, assessment_id)
            guest = self.learning.reauthorize(db, token)
            now = self.learning.clock()
            self._freeze_due(db, guest, record, now)
            return assessment_view(record, now, device_id)

    def activate(
        self, token: str | None, assessment_id: str, request: WriterRequest, key: str | None
    ) -> StoredResponse:
        def start(
            db: Session, guest: Guest, record: AssessmentRecord, now: datetime
        ) -> AssessmentView:
            self._writer(record, request)
            if record.status not in {"prepared", "active"}:
                raise ApiError(409, "assessment_closed", "Приём черновиков уже завершён.")
            if record.status == "prepared":
                record.started_at = now
                record.deadline_at = (
                    now + timedelta(minutes=record.duration_minutes) if record.mode == "exam"
                    else None
                )
                record.status = "active"
            return assessment_view(record, now, str(request.device_id))

        return self._mutate(token, assessment_id, request, key, "activate", start)

    def takeover(
        self, token: str | None, assessment_id: str, request: WriterRequest, key: str | None
    ) -> StoredResponse:
        def adopt(
            db: Session, guest: Guest, record: AssessmentRecord, now: datetime
        ) -> AssessmentView:
            if record.status == "completed":
                raise ApiError(409, "assessment_closed", "Завершённый снимок нельзя менять.")
            if request.writer_generation != record.writer_generation:
                raise ApiError(
                    409, "assessment_writer_conflict", "Управление уже передано. Обновите сессию."
                )
            record.writer_device_id = str(request.device_id)
            record.writer_generation += 1
            return assessment_view(record, now, str(request.device_id))

        return self._mutate(token, assessment_id, request, key, "takeover", adopt)

    def _validate_answers(
        self, record: AssessmentRecord, answers: dict[str, DraftAnswer]
    ) -> None:
        known = {task["id"] for task in record.tasks_snapshot}
        if not answers.keys() <= known:
            raise ApiError(422, "assessment_unknown_task", "Черновик содержит чужую задачу.")
        if any(item.active_seconds > self.learning.settings.max_active_seconds
               for item in answers.values()):
            raise ApiError(
                422, "invalid_active_seconds", "Превышен предел активного времени задачи."
            )

    def _remember_first_drafts(
        self, db: Session, guest: Guest, record: AssessmentRecord, answers: dict[str, Any],
        *, at: datetime,
    ) -> None:
        """Keep first-input history; final eligibility is sampled separately."""
        first = dict(record.first_drafts)
        contexts = dict(record.answer_context)
        now = at.isoformat()
        owners = self.learning.owner_ids(db, guest)
        tasks = {task["id"]: task for task in record.tasks_snapshot}
        for task_id, draft in answers.items():
            if task_id not in first:
                first[task_id] = {**draft, "recorded_at": now}
            if task_id in contexts:
                continue
            try:
                parse_answer(draft["answer"], "exam")
            except AnswerFormatError:
                continue
            aliases = aliases_for_task(db, owners, tasks[task_id], tasks=record.tasks_snapshot)
            contexts[task_id] = {
                "assisted": any(
                    item.assistance_seen or item.reference_seen
                    for item in aliases.records
                ),
                "first_answer": {**draft, "recorded_at": now},
                "owner_ids": list(owners),
            }
        record.first_drafts = first
        record.answer_context = contexts

    def draft(
        self, token: str | None, assessment_id: str, request: DraftRequest
    ) -> StoredResponse:
        with (
            self.learning.observe_save("draft_save") as observation,
            self.learning._guest_transaction(token, write=True) as (db, guest),
        ):
            record = self._owned(db, guest, assessment_id)
            guest = self.learning.reauthorize(db, token)
            now = self.learning.clock()
            self._freeze_due(db, guest, record, now)
            try:
                self._writer(record, request)
                if record.status != "active":
                    raise ApiError(
                        409, "assessment_not_active", "Черновики принимаются только до завершения."
                    )
                self._validate_answers(record, request.answers)
                if request.expected_revision != record.draft_revision:
                    raise ApiError(
                        409, "assessment_draft_conflict",
                        "Черновик уже изменён. Сохраните локальный ввод и обновите сессию.",
                    )
                answers = {
                    task_id: {
                        "answer": draft.answer,
                        "active_seconds": max(
                            record.drafts.get(task_id, {}).get("active_seconds", 0),
                            draft.active_seconds,
                        ),
                    }
                    for task_id, draft in request.answers.items()
                }
                observation.attempted = True
                self._remember_first_drafts(db, guest, record, answers, at=now)
                record.drafts = {**record.drafts, **answers}
                record.current_index = request.current_index
                record.draft_revision += 1
                response = StoredResponse(200, json_text(assessment_view(
                    record, now, str(request.device_id)
                )))
                observation.success = True
            except ApiError as exc:
                if exc.status_code == 401:
                    raise
                response = StoredResponse(exc.status_code, json_text(exc.response()))
        return response

    def _assisted_tasks(
        self, db: Session, guest: Guest, record: AssessmentRecord
    ) -> set[str]:
        """Resolve frozen conditions across current origins under the root lock."""
        owners = self.learning.owner_ids(db, guest)
        return {
            task["id"] for task in record.tasks_snapshot
            if any(item.assistance_seen or item.reference_seen for item in aliases_for_task(
                db, owners, task, tasks=record.tasks_snapshot,
            ).records)
        }

    def _prior_numeric(
        self, db: Session, guest: Guest, record: AssessmentRecord, at: datetime
    ) -> set[str]:
        owners = self.learning.owner_ids(db, guest)
        prior = prior_numeric_ids(db, owners, at=at, exclude_assessment_id=record.id)
        # Pending canonical snapshots reserve their instances as well. They do
        # not enter learning projections until release, but two frozen exams
        # must not both claim an independent answer to the same instance.
        return {
            task["id"] for task in record.tasks_snapshot
            if prior & aliases_for_task(db, owners, task, tasks=record.tasks_snapshot).ids
        }

    def finish(
        self, token: str | None, assessment_id: str, request: FinishRequest, key: str | None
    ) -> StoredResponse:
        def complete(
            db: Session, guest: Guest, record: AssessmentRecord, now: datetime
        ) -> AssessmentView:
            self._writer(record, request)
            self._validate_answers(record, request.answers)
            if record.status == "prepared":
                raise ApiError(409, "assessment_not_active", "Сначала подтвердите начало сессии.")
            snapshot = complete_snapshot(record, request.model_dump(mode="json")["answers"])
            finish_hash = content_hash({
                "answers": snapshot, "connection_lost": request.connection_lost,
            })
            if record.finish_hash is not None:
                if finish_hash != record.finish_hash:
                    raise ApiError(
                        409, "assessment_snapshot_conflict",
                        "Итоговый снимок уже заморожен. Другое содержимое не принимается.",
                    )
                return assessment_view(record, now, str(request.device_id))

            late = record.server_result is not None
            server = record.server_result
            local = None
            assisted_tasks = self._assisted_tasks(db, guest, record)
            if server is None:
                server_answers = (
                    complete_snapshot(record, record.drafts)
                    if request.connection_lost else snapshot
                )
                self._remember_first_drafts(db, guest, record, server_answers, at=now)
                server = build_result(
                    record, server_answers, at=now, source="server",
                    reason="connection_lost" if request.connection_lost else "finished",
                    prior_numeric=self._prior_numeric(db, guest, record, now),
                    assisted_tasks=assisted_tasks,
                    operation_health=self.learning.operation_health,
                ).model_dump(mode="json")
                record.drafts = server_answers
            if late or request.connection_lost:
                self._remember_first_drafts(db, guest, record, snapshot, at=now)
                local = build_result(
                    record, snapshot, at=now, source="local", reason="connection_lost",
                    prior_numeric=set(), assisted_tasks=assisted_tasks,
                    operation_health=self.learning.operation_health,
                ).model_dump(mode="json")

            record.server_result = server
            record.local_result = local
            record.finish_hash = finish_hash
            record.released_at = now
            record.status = "completed"
            for seen in db.scalars(select(SeenTask).where(
                SeenTask.guest_id == record.guest_id,
                SeenTask.task_id.in_(snapshot),
            )):
                seen.reference_seen = True
            return assessment_view(record, now, str(request.device_id))

        return self._mutate(token, assessment_id, request, key, "finish", complete)

    def _freeze_due(
        self, db: Session, guest: Guest, record: AssessmentRecord, now: datetime
    ) -> bool:
        if (record.status != "active" or record.deadline_at is None
                or record.deadline_at > now):
            return False
        # A late worker records the deadline, not its wake-up time. No locally
        # supplied final answers are involved, and no reference exposure is set.
        self._remember_first_drafts(db, guest, record, record.drafts, at=record.deadline_at)
        snapshot = complete_snapshot(record, record.drafts)
        frozen = build_result(
            record, snapshot, at=record.deadline_at, source="server", reason="deadline",
            prior_numeric=self._prior_numeric(db, guest, record, record.deadline_at),
            assisted_tasks=self._assisted_tasks(db, guest, record),
            operation_health=self.learning.operation_health,
        )
        record.server_result = frozen.model_dump(mode="json")
        record.status = "awaiting_snapshot"
        return True

    def reconcile_deadlines(self, *, limit: int = 100) -> int:
        """Freeze due exams without browser traffic; safe across restarts/workers.

        The unlocked scan is only a candidate list. Each short write transaction
        locks the canonical root first, rechecks ownership, then locks the exam.
        Never acquire an assessment lock before the account's root lock.
        """
        if limit < 1:
            raise ValueError("limit must be positive")
        with self.learning.database.transaction() as db:
            candidates = list(db.execute(select(
                AssessmentRecord.id, AssessmentRecord.guest_id,
            ).where(
                AssessmentRecord.status == "active",
                AssessmentRecord.deadline_at <= self.learning.clock(),
            ).order_by(AssessmentRecord.deadline_at, AssessmentRecord.id).limit(limit)))
        frozen = 0
        for assessment_id, origin in candidates:
            with self.learning.database.transaction(write=True) as db:
                root_id = root_owner_id(db, origin)
                root = db.scalar(select(Guest).where(Guest.id == root_id)
                                 .with_for_update(skip_locked=True)
                                 .execution_options(populate_existing=True))
                if root is None or root_owner_id(db, origin) != root_id:
                    # A concurrent claim may have changed the canonical lock
                    # while we waited. Retry via the next scheduled scan.
                    continue
                record = db.scalar(select(AssessmentRecord).where(
                    AssessmentRecord.id == assessment_id,
                ).with_for_update().execution_options(populate_existing=True))
                if record is not None:
                    frozen += self._freeze_due(db, root, record, self.learning.clock())
        return frozen

    def prepare(
        self, token: str | None, request: PrepareRequest, key: str | None
    ) -> StoredResponse:
        with self.learning._guest_transaction(token, write=True) as (db, guest):

            def create() -> AssessmentView:
                bundle = self.learning.locked_content(db, token)
                slots = bundle.profile.slots
                if len(slots) != 13 or len({slot.number for slot in slots}) != 13:
                    raise ApiError(
                        503, "assessment_profile_invalid",
                        "Для диагностики и пробника нужен профиль ровно из 13 позиций.",
                    )
                available = bundle.available_tasks(
                    allow_demo_content=self.learning.settings.allow_demo_content
                )
                owners = self.learning.owner_ids(db, guest)
                now = self.learning.clock()
                normalized_key = request_uuid(key)
                exposure = recent_exposure(db, owners, bundle.tasks, now)
                signatures = {task.id: instance_key(task) for task in available}
                candidates = {
                    slot.number: sorted(
                        (task for task in available if task.slot == slot.number),
                        key=lambda task: hashlib.sha256(
                            f"{guest.id}:{normalized_key}:{task.id}".encode()
                        ).digest(),
                    ) for slot in slots
                }
                selected = {}
                used_ids, used_keys = set(), set()
                for slot in slots:
                    fresh = next((task for task in candidates[slot.number]
                                  if task.id not in used_ids | exposure.ids
                                  and signatures[task.id] not in used_keys | exposure.keys), None)
                    if fresh is not None:
                        selected[slot.number] = fresh
                        used_ids.add(fresh.id)
                        used_keys.add(signatures[fresh.id])
                missing = [slot.number for slot in slots if slot.number not in selected]
                if missing:
                    generated, _ = generate_candidates(
                        self.learning, db, guest,
                        CreateSessionRequest(slots=missing, length=20, mode="practice"),
                        normalized_key, bundle, exclude=exposure.ids | used_ids,
                        exclude_tasks=tuple(selected.values()), limit=len(missing),
                        slot_limits=dict.fromkeys(missing, 1), now=now,
                    )
                    for task in generated:
                        signature = instance_key(task)
                        if (task.slot in missing and task.slot not in selected
                                and task.id not in used_ids and signature not in used_keys):
                            selected[task.slot] = task
                            used_ids.add(task.id)
                            used_keys.add(signature)
                repeated = []
                for number in missing:
                    if number in selected:
                        continue
                    # Historical assessments allow a static repeat only after
                    # exhausting fresh static and bounded runtime candidates.
                    fallback = next((task for task in candidates[number]
                                     if task.id not in used_ids
                                     and signatures[task.id] not in used_keys), None)
                    if fallback is None:
                        raise ApiError(
                            409, "assessment_bank_incomplete",
                            "В банке нет задачи для каждой из 13 позиций. "
                            "Сокращённый пробник не создаётся.",
                        )
                    selected[number] = fallback
                    used_ids.add(fallback.id)
                    used_keys.add(signatures[fallback.id])
                    repeated.append(number)
                tasks = [selected[slot.number] for slot in slots]
                record = AssessmentRecord(
                    id=str(uuid4()), guest_id=guest.id, profile_id=bundle.profile.id,
                    profile_revision=bundle.profile.revision,
                    profile_snapshot=bundle.profile.model_dump(mode="json"),
                    tasks_snapshot=[task.model_dump(mode="json") for task in tasks],
                    mode=request.mode, status="prepared", created_at=now,
                    started_at=None, deadline_at=None, released_at=None,
                    duration_minutes=request.duration_minutes,
                    writer_device_id=str(request.device_id), writer_generation=1,
                    draft_revision=0, current_index=0, drafts={}, first_drafts={},
                    answer_context={}, server_result=None, local_result=None, finish_hash=None,
                )
                db.add(record)
                db.flush()
                mark_instances(db, record.guest_id, tasks, now)
                db.flush()
                prepared = assessment_view(record, now, str(request.device_id))
                if repeated:
                    prepared.result_notice += (
                        " Повторные статические условия в позициях: "
                        + ", ".join(map(str, repeated))
                        + ". Предыдущие ответы и помощь учитываются при оценке самостоятельности."
                    )
                return prepared

            return self.learning._idempotent(
                db, guest, key, "POST /assessments", request, create
            )
