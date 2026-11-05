"""Guest ownership, transactional idempotency and the practice lifecycle.

Every write first locks the guest row on PostgreSQL. SQLite reserves its write
transaction before the first read. The same lock therefore protects task
selection, first attempts, assistance, revisions and idempotency across workers,
not merely threads in a single application process.
"""

import hashlib
import json
import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checker import AnswerFormatError, check_answer, parse_answer
from app.config import Settings
from app.content import ContentBundle, ContentError, load_content
from app.database import Database
from app.errors import ApiError, not_found
from app.models import (
    AttemptRecord,
    Guest,
    IdempotencyRecord,
    LearningSessionRecord,
    SeenTask,
)
from app.presentation import attempt_view, session_view, summary_view
from app.schemas import (
    AttemptRequest,
    CreateSessionRequest,
    DraftRequest,
    DraftRevision,
    Export,
    Hint,
    HintRequest,
    LearningSession,
    Progress,
    Solution,
    SolutionRequest,
)

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_UUID = re.compile(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")


def utc_now() -> datetime:
    return datetime.now(UTC)


def token_digest(token: str | None) -> str | None:
    if token is None or not _TOKEN.fullmatch(token):
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def request_uuid(value: str | None) -> str:
    if value is None or not _UUID.fullmatch(value):
        raise ApiError(422, "invalid_idempotency_key", "Idempotency-Key должен быть UUID.")
    return str(UUID(value))


def json_text(value: BaseModel | dict[str, Any]) -> str:
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class StoredResponse:
    status_code: int
    content: str


class LearningService:
    def __init__(
        self, database: Database, settings: Settings, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock

    def content(self) -> ContentBundle:
        try:
            return load_content(self.settings.content_dir)
        except ContentError as exc:
            raise ApiError(503, "content_unavailable", "Учебный пакет сейчас недоступен.") from exc

    @contextmanager
    def _guest_transaction(self, token: str | None, *, write: bool = False) -> Iterator[tuple]:
        digest = token_digest(token)
        if digest is None:
            raise ApiError(401, "guest_required", "Сначала начните гостевой сеанс.")
        with self.database.transaction(write=write) as db:
            statement = select(Guest).where(Guest.token_digest == digest)
            if write:
                statement = statement.with_for_update()
            guest = db.scalar(statement)
            if guest is None or guest.expires_at <= self.clock():
                raise ApiError(401, "guest_required", "Гостевой сеанс отсутствует или истёк.")
            if write:
                guest.last_seen_at = self.clock()
            yield db, guest

    def guest(self, token: str | None) -> tuple[Guest, str, int]:
        now = self.clock()
        with self.database.transaction(write=True) as db:
            digest = token_digest(token)
            existing = (
                db.scalar(select(Guest).where(Guest.token_digest == digest).with_for_update())
                if digest is not None
                else None
            )
            if existing is not None and existing.expires_at > now:
                existing.last_seen_at = now
                return existing, token, max(1, int((existing.expires_at - now).total_seconds()))
            new_token = secrets.token_urlsafe(32)
            lifetime = self.settings.guest_access_days * 86_400
            created = Guest(
                id=str(uuid4()),
                token_digest=token_digest(new_token),
                created_at=now,
                expires_at=now + timedelta(seconds=lifetime),
                last_seen_at=now,
            )
            db.add(created)
            db.flush()
            return created, new_token, lifetime

    @staticmethod
    def _owned(db: Session, guest: Guest, session_id: str) -> LearningSessionRecord:
        session = db.scalar(
            select(LearningSessionRecord).where(
                LearningSessionRecord.id == session_id,
                LearningSessionRecord.guest_id == guest.id,
            )
        )
        if session is None:
            raise not_found()
        return session

    @staticmethod
    def _attempts(db: Session, session_id: str) -> list[AttemptRecord]:
        return list(
            db.scalars(
                select(AttemptRecord)
                .where(AttemptRecord.session_id == session_id)
                .order_by(AttemptRecord.sequence)
            )
        )

    @staticmethod
    def _active(session: LearningSessionRecord) -> None:
        if session.status != "active":
            raise ApiError(409, "session_completed", "Завершённую сессию нельзя менять.")

    @staticmethod
    def _task(session: LearningSessionRecord, task_id: str) -> tuple[int, dict[str, Any]]:
        for index, task in enumerate(session.tasks_snapshot):
            if task["id"] == task_id:
                return index, task
        raise not_found()

    def _bounded_seconds(self, seconds: int) -> None:
        if seconds > self.settings.max_active_seconds:
            raise ApiError(
                422, "invalid_active_seconds", "Превышен предел активного времени задачи."
            )

    @staticmethod
    def _track_time(session: LearningSessionRecord, task_id: str, reported: int) -> int:
        cumulative = max(session.active_seconds.get(task_id, 0), reported)
        session.active_seconds = {**session.active_seconds, task_id: cumulative}
        return cumulative

    def _idempotent(
        self,
        db: Session,
        guest: Guest,
        key: str | None,
        operation: str,
        body: BaseModel,
        action: Callable[[], BaseModel],
    ) -> StoredResponse:
        normalized_key = request_uuid(key)
        canonical = json.dumps(
            {"operation": operation, "body": body.model_dump(mode="json")},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        prior = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.guest_id == guest.id,
                IdempotencyRecord.request_key == normalized_key,
            )
        )
        if prior is not None:
            if prior.request_hash != request_hash:
                raise ApiError(
                    409, "idempotency_conflict", "Этот ключ уже использован с другим телом запроса."
                )
            return StoredResponse(prior.status_code, prior.response_json)
        try:
            output = StoredResponse(200, json_text(action()))
        except ApiError as exc:
            output = StoredResponse(exc.status_code, json_text(exc.response()))
        db.add(
            IdempotencyRecord(
                id=str(uuid4()), guest_id=guest.id, request_key=normalized_key,
                request_hash=request_hash, operation=operation, status_code=output.status_code,
                response_json=output.content, created_at=self.clock(),
            )
        )
        db.flush()
        return output

    def create_session(
        self, token: str | None, request: CreateSessionRequest, key: str | None
    ) -> StoredResponse:
        with self._guest_transaction(token, write=True) as (db, guest):

            def create() -> LearningSession:
                bundle = self.content()
                valid_slots = {slot.number for slot in bundle.profile.slots}
                if not set(request.slots) <= valid_slots:
                    raise ApiError(422, "invalid_slots", "Позиция отсутствует в текущем профиле.")
                if not self.settings.allow_demo_content:
                    raise ApiError(
                        503, "demo_content_disabled",
                        "Демонстрационный банк выключен. Нужна настройка ALLOW_DEMO_CONTENT=true.",
                    )
                now = self.clock()
                seen_records = {
                    record.task_id: record
                    for record in db.scalars(select(SeenTask).where(SeenTask.guest_id == guest.id))
                }
                cutoff = now - timedelta(days=30)
                excluded = {
                    task_id for task_id, seen in seen_records.items() if seen.last_seen_at > cutoff
                }
                groups = {
                    slot: [
                        task for task in bundle.available_tasks(allow_demo_content=True)
                        if task.slot == slot and task.id not in excluded
                    ]
                    for slot in request.slots
                }
                for group in groups.values():
                    group.sort(
                        key=lambda task: hashlib.sha256(
                            f"{guest.id}:{key}:{task.id}".encode()
                        ).digest()
                    )
                selected = []
                while len(selected) < request.length and any(groups.values()):
                    for slot in request.slots:
                        if groups[slot] and len(selected) < request.length:
                            selected.append(groups[slot].pop())
                if not selected:
                    raise ApiError(
                        409, "bank_exhausted",
                        "Нет новых подходящих экземпляров: уже выданные за 30 дней исключены. "
                        "Выберите другие позиции или дождитесь расширения банка.",
                    )
                notice = None
                if len(selected) < request.length:
                    notice = (
                        f"В банке доступно {len(selected)} из {request.length} задач. "
                        "Уже выданные за 30 дней экземпляры исключены; скрытых повторов нет."
                    )
                session = LearningSessionRecord(
                    id=str(uuid4()), guest_id=guest.id, profile_id=bundle.profile.id,
                    profile_revision=bundle.profile.revision,
                    profile_snapshot=bundle.profile.model_dump(mode="json"), mode="practice",
                    status="active", created_at=now, completed_at=None, current_index=0,
                    requested_length=request.length, notice=notice, draft_revision=0,
                    tasks_snapshot=[task.model_dump(mode="json") for task in selected],
                    drafts={}, help_state={}, active_seconds={}, summary_snapshot=None,
                )
                db.add(session)
                for task in selected:
                    if task.id in seen_records:
                        seen_records[task.id].last_seen_at = now
                    else:
                        db.add(
                            SeenTask(
                                id=str(uuid4()), guest_id=guest.id, task_id=task.id,
                                first_seen_at=now, last_seen_at=now,
                                assistance_seen=False, reference_seen=False,
                            )
                        )
                db.flush()
                return session_view(session, [])

            return self._idempotent(db, guest, key, "POST /sessions", request, create)

    def get_session(self, token: str | None, session_id: str) -> LearningSession:
        with self._guest_transaction(token) as (db, guest):
            session = self._owned(db, guest, session_id)
            return session_view(session, self._attempts(db, session.id))

    def draft(self, token: str | None, session_id: str, request: DraftRequest) -> DraftRevision:
        with self._guest_transaction(token, write=True) as (db, guest):
            session = self._owned(db, guest, session_id)
            self._active(session)
            index, _ = self._task(session, request.task_id)
            self._bounded_seconds(request.active_seconds)
            if session.draft_revision != request.expected_revision:
                raise ApiError(
                    409, "draft_conflict",
                    "Черновик уже изменён. Сохраните локальный ввод и обновите сессию."
                )
            cumulative = self._track_time(session, request.task_id, request.active_seconds)
            session.drafts = {
                **session.drafts,
                request.task_id: {"answer": request.answer, "active_seconds": cumulative},
            }
            session.current_index = index
            session.draft_revision += 1
            return DraftRevision(draft_revision=session.draft_revision)

    def attempt(
        self, token: str | None, session_id: str, request: AttemptRequest, key: str | None
    ) -> StoredResponse:
        with self._guest_transaction(token, write=True) as (db, guest):
            session = self._owned(db, guest, session_id)

            def submit() -> BaseModel:
                self._active(session)
                _, task = self._task(session, request.task_id)
                self._bounded_seconds(request.active_seconds)
                if request.skipped and request.answer != "":
                    raise ApiError(
                        422, "invalid_skip", "При пропуске ответ должен быть пустым.", "answer"
                    )
                try:
                    result = (
                        None if request.skipped else check_answer(request.answer, task["answer"])
                    )
                except AnswerFormatError as exc:
                    raise ApiError(422, exc.code, str(exc), "answer") from exc
                attempts = self._attempts(db, session.id)
                previous = [attempt for attempt in attempts if attempt.task_id == request.task_id]
                seen = db.scalar(
                    select(SeenTask).where(
                        SeenTask.guest_id == guest.id, SeenTask.task_id == task["id"]
                    )
                )
                if seen is None:
                    raise ApiError(
                        503, "state_unavailable", "Не удалось восстановить историю задачи."
                    )
                assisted = seen.assistance_seen or seen.reference_seen
                prior_numeric = db.scalar(
                    select(AttemptRecord.id).where(
                        AttemptRecord.guest_id == guest.id,
                        AttemptRecord.task_id == request.task_id,
                        AttemptRecord.skipped.is_(False),
                    ).limit(1)
                )
                cumulative = self._track_time(session, request.task_id, request.active_seconds)
                record = AttemptRecord(
                    id=str(uuid4()), guest_id=guest.id, session_id=session.id,
                    task_id=request.task_id, task_revision=task["revision"], sequence=len(attempts),
                    raw_answer=request.answer,
                    normalized_answer=result.normalized_answer if result else None,
                    correct=result.correct if result else False,
                    assisted=assisted, first_attempt=not previous,
                    independent=(
                        not request.skipped and not previous and not assisted
                        and prior_numeric is None
                    ),
                    skipped=request.skipped, active_seconds=cumulative, created_at=self.clock(),
                    checker_revision="fraction-v1",
                    expected_answer=parse_answer(task["answer"], "exam").normalized_answer,
                    solution=task["solution"],
                )
                db.add(record)
                seen.reference_seen = True
                handled = {attempt.task_id for attempt in [*attempts, record]}
                session.current_index = next(
                    (index for index, item in enumerate(session.tasks_snapshot)
                     if item["id"] not in handled),
                    len(session.tasks_snapshot) - 1,
                )
                db.flush()
                return attempt_view(record)

            return self._idempotent(
                db, guest, key, f"POST /sessions/{session.id}/attempts", request, submit
            )

    def _help(
        self, token: str | None, session_id: str, task_id: str, level: int | None
    ) -> Hint | Solution:
        with self._guest_transaction(token, write=True) as (db, guest):
            session = self._owned(db, guest, session_id)
            self._active(session)
            _, task = self._task(session, task_id)
            state = session.help_state.get(task_id, {"hints": [], "solution": None})
            if level is not None:
                result = Hint(level=level, text=task["hints"][level - 1])
                hints = {hint["level"]: hint for hint in state["hints"]}
                hints[level] = result.model_dump()
                state = {**state, "hints": [hints[index] for index in sorted(hints)]}
            else:
                result = Solution(
                    answer=parse_answer(task["answer"], "exam").normalized_answer,
                    steps=task["solution"],
                )
                state = {**state, "solution": result.model_dump()}
            seen = db.scalar(
                select(SeenTask).where(SeenTask.guest_id == guest.id, SeenTask.task_id == task_id)
            )
            if seen is None:
                raise ApiError(503, "state_unavailable", "Не удалось восстановить историю задачи.")
            session.help_state = {**session.help_state, task_id: state}
            seen.assistance_seen = True
            if level is None:
                seen.reference_seen = True
            return result

    def hint(self, token: str | None, session_id: str, request: HintRequest) -> Hint:
        return self._help(token, session_id, request.task_id, request.level)

    def solution(self, token: str | None, session_id: str, request: SolutionRequest) -> Solution:
        return self._help(token, session_id, request.task_id, None)

    def finish(
        self, token: str | None, session_id: str, request: BaseModel, key: str | None
    ) -> StoredResponse:
        with self._guest_transaction(token, write=True) as (db, guest):
            session = self._owned(db, guest, session_id)

            def complete() -> LearningSession:
                attempts = self._attempts(db, session.id)
                if session.status == "active":
                    session.summary_snapshot = summary_view(session, attempts).model_dump()
                    session.status = "completed"
                    session.completed_at = self.clock()
                return session_view(session, attempts)

            return self._idempotent(
                db, guest, key, f"POST /sessions/{session.id}/finish", request, complete
            )

    def _history(self, db: Session, guest: Guest) -> tuple[list, list]:
        sessions = list(
            db.scalars(
                select(LearningSessionRecord).where(LearningSessionRecord.guest_id == guest.id)
                .order_by(LearningSessionRecord.created_at.desc(), LearningSessionRecord.id.desc())
            )
        )
        attempts = list(
            db.scalars(
                select(AttemptRecord).where(AttemptRecord.guest_id == guest.id)
                .order_by(
                    AttemptRecord.created_at, AttemptRecord.session_id, AttemptRecord.sequence
                )
            )
        )
        return sessions, attempts

    def progress(self, token: str | None) -> Progress:
        bundle = self.content()
        with self._guest_transaction(token) as (db, guest):
            sessions, attempts = self._history(db, guest)
            snapshots = {
                (session.id, task["id"]): task
                for session in sessions for task in session.tasks_snapshot
            }
            independent = [attempt for attempt in attempts if attempt.independent]
            slots = []
            for slot in bundle.profile.slots:
                relevant = [
                    attempt for attempt in independent
                    if snapshots[(attempt.session_id, attempt.task_id)]["slot"] == slot.number
                ]
                latest = relevant[-5:]
                status = "Нет данных" if not relevant else (
                    "Закрепляю" if sum(attempt.correct for attempt in latest) >= 3 else "Изучаю"
                )
                covered = {
                    skill for attempt in relevant if attempt.correct
                    for skill in snapshots[(attempt.session_id, attempt.task_id)]["skill_ids"]
                }
                slots.append({
                    "number": slot.number, "attempts": len(relevant),
                    "correct": sum(attempt.correct for attempt in relevant), "status": status,
                    "covered_skills": len(covered & {skill.id for skill in slot.skills}),
                    "total_skills": len(slot.skills),
                })
            by_session = {
                session.id: [attempt for attempt in attempts if attempt.session_id == session.id]
                for session in sessions
            }
            summaries = {
                session.id: summary_view(session, by_session[session.id]) for session in sessions
            }
            mistakes = [
                {"task": snapshots[(attempt.session_id, attempt.task_id)],
                 "attempt": attempt_view(attempt)}
                for attempt in reversed(attempts)
                if attempt.skipped or (attempt.first_attempt and not attempt.correct)
            ]
            # Convert the task with the same explicit public allowlist used by sessions.
            from app.content import public_task

            for mistake in mistakes:
                mistake["task"] = public_task(mistake["task"])
            return Progress(
                independent_total=len(independent),
                independent_correct=sum(a.correct for a in independent),
                assisted_total=sum(summary.assisted for summary in summaries.values()),
                corrections_total=sum(summary.corrections for summary in summaries.values()),
                skipped_total=sum(summary.skipped for summary in summaries.values()),
                active_session_id=next((s.id for s in sessions if s.status == "active"), None),
                slots=slots,
                recent_sessions=[
                    {"id": session.id, "status": session.status,
                     "created_at": session.created_at.isoformat(),
                     "summary": summaries[session.id]}
                    for session in sessions[:20]
                ],
                mistakes=mistakes,
            )

    def export(self, token: str | None) -> Export:
        bundle = self.content()
        with self._guest_transaction(token) as (db, guest):
            sessions, attempts = self._history(db, guest)
            return Export(
                version="1", exported_at=self.clock().isoformat(), profile_id=bundle.profile.id,
                sessions=[session_view(session, [a for a in attempts if a.session_id == session.id])
                          for session in sessions],
            )
