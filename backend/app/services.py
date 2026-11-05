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
from functools import cached_property
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import AccessSession
from app.accounts.principals import owner_ids, resolve_guest
from app.checker import AnswerFormatError, check_answer, parse_answer
from app.config import Settings
from app.content import ContentBundle, ContentError
from app.database import Database
from app.editor.repository import lock_catalog
from app.eligibility import prior_numeric_ids
from app.errors import ApiError, not_found
from app.instances import aliases_for_task
from app.models import (
    AttemptRecord,
    Guest,
    IdempotencyRecord,
    LearningSessionRecord,
)
from app.operations.health import OperationHealth
from app.practice import mark_seen, select_tasks
from app.presentation import attempt_view, session_view, summary_view
from app.schemas import (
    AttemptRequest,
    CreateSessionRequest,
    DraftRequest,
    DraftRevision,
    Hint,
    HintRequest,
    IdentityResponse,
    LearningSession,
    Progress,
    Solution,
    SolutionRequest,
)

if TYPE_CHECKING:
    from app.history import HistoryExport
    from app.learning.service import LearningExtrasService

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


@dataclass(slots=True)
class SaveObservation:
    attempted: bool = False
    success: bool = False


class LearningService:
    def __init__(
        self, database: Database, settings: Settings, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self.database = database
        self.settings = settings
        self.clock = clock
        self.operation_health = OperationHealth(now=clock())

    @contextmanager
    def observe_save(self, name: str) -> Iterator[SaveObservation]:
        observation = SaveObservation()
        try:
            yield observation
        except Exception:
            if observation.attempted:
                self.operation_health.record_event(name, success=False)
            raise
        else:
            if observation.attempted:
                self.operation_health.record_event(name, success=observation.success)

    def reauthorize(
        self, db: Session, token: str | None, *, write: bool = True,
    ) -> Guest:
        return resolve_guest(db, token, self.clock(), write=write, clock=self.clock)

    def locked_content(self, db: Session, token: str | None) -> ContentBundle:
        lock_catalog(db)
        self.reauthorize(db, token)
        return self.content(db)

    @staticmethod
    def owner_ids(db: Session, guest: Guest) -> list[str]:
        return owner_ids(db, guest)

    def identity(self, token: str | None) -> IdentityResponse:
        with self._guest_transaction(token) as (db, guest):
            return IdentityResponse(
                id=guest.id,
                kind="guest" if guest.token_digest == token_digest(token) else "account",
                owner_ids=self.owner_ids(db, guest),
            )

    @cached_property
    def extras(self) -> "LearningExtrasService":
        from app.learning.service import LearningExtrasService

        return LearningExtrasService(self)

    def content(self, db: Session | None = None) -> ContentBundle:
        from app.editor.repository import combined_content

        try:
            if db is not None:
                return combined_content(db, self.settings)
            with self.database.transaction() as transaction:
                return combined_content(transaction, self.settings)
        except ContentError as exc:
            raise ApiError(503, "content_unavailable", "Учебный пакет сейчас недоступен.") from exc

    @contextmanager
    def _guest_transaction(self, token: str | None, *, write: bool = False) -> Iterator[tuple]:
        with self.database.transaction(write=write) as db:
            guest = resolve_guest(db, token, self.clock(), write=write, clock=self.clock)
            yield db, guest

    def guest(self, token: str | None) -> tuple[Guest, str, int]:
        with self.database.transaction(write=True) as db:
            try:
                existing = resolve_guest(db, token, self.clock(), write=True, clock=self.clock)
            except ApiError as exc:
                if exc.status_code != 401:
                    raise
            else:
                now = self.clock()
                access = db.scalar(select(AccessSession).where(
                    AccessSession.token_digest == token_digest(token),
                ))
                expires_at = access.expires_at if access else existing.expires_at
                return existing, token, max(1, int((expires_at - now).total_seconds()))
            now = self.clock()
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
                LearningSessionRecord.guest_id.in_(owner_ids(db, guest)),
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
            {"operation": operation, "body": body.model_dump(mode="json", exclude_unset=True)},
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        previous = list(db.scalars(
            select(IdempotencyRecord).where(
                IdempotencyRecord.guest_id.in_(self.owner_ids(db, guest)),
                IdempotencyRecord.request_key == normalized_key,
            ).order_by(IdempotencyRecord.created_at, IdempotencyRecord.id)
        ))
        if previous:
            matches = [record for record in previous if record.request_hash == request_hash
                       and record.operation == operation]
            if not matches:
                raise ApiError(
                    409, "idempotency_conflict", "Этот ключ уже использован с другим телом запроса."
                )
            if len({(record.status_code, record.response_json) for record in matches}) > 1:
                raise ApiError(
                    409, "idempotency_ambiguous",
                    "В объединённой истории совпали ключи разных запросов. "
                    "Откройте сохранённое занятие из истории.",
                )
            prior = matches[0]
            return StoredResponse(prior.status_code, prior.response_json)
        try:
            with db.begin_nested():
                output = StoredResponse(200, json_text(action()))
        except ApiError as exc:
            if exc.status_code == 401:
                raise
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
                bundle = self.locked_content(db, token)
                selected, notice = select_tasks(
                    self, db, guest, request, request_uuid(key), bundle,
                )
                now = self.clock()
                session = LearningSessionRecord(
                    id=str(uuid4()), guest_id=guest.id, profile_id=bundle.profile.id,
                    profile_revision=bundle.profile.revision,
                    profile_snapshot=bundle.profile.model_dump(mode="json"), mode="practice",
                    status="active", created_at=now, completed_at=None, current_index=0,
                    requested_length=request.length, notice=notice, draft_revision=0,
                    tasks_snapshot=[task.model_dump(mode="json") for task in selected],
                    options_snapshot=request.model_dump(mode="json"),
                    drafts={}, help_state={}, active_seconds={}, summary_snapshot=None,
                )
                db.add(session)
                mark_seen(self, db, session.guest_id, selected)
                db.flush()
                return session_view(session, [])

            return self._idempotent(db, guest, key, "POST /sessions", request, create)

    def extend(
        self, token: str | None, session_id: str, body: BaseModel, key: str | None,
    ) -> StoredResponse:
        with self._guest_transaction(token, write=True) as (db, guest):
            session = self._owned(db, guest, session_id)

            def append() -> LearningSession:
                self._active(session)
                options = session.options_snapshot
                if not options or not options.get("until_stopped"):
                    raise ApiError(409, "fixed_length", "Эта серия имеет заданную длину.")
                if len(session.tasks_snapshot) >= 1_000:
                    raise ApiError(409, "session_limit", "Завершите это занятие и начните новое.")
                attempts = self._attempts(db, session.id)
                handled = {attempt.task_id for attempt in attempts}
                if any(task["id"] not in handled for task in session.tasks_snapshot):
                    raise ApiError(
                        409, "unfinished_batch", "Ответьте или пропустите текущие задачи."
                    )
                bundle = self.locked_content(db, token)
                if (bundle.profile.id, bundle.profile.revision) != (
                    session.profile_id, session.profile_revision,
                ):
                    raise ApiError(
                        409, "profile_changed",
                        "Профиль обновлён. Завершите это занятие перед новым.",
                    )
                selected, notice = select_tasks(
                    self, db, guest, CreateSessionRequest.model_validate(options),
                    request_uuid(key), bundle,
                    exclude=frozenset(task["id"] for task in session.tasks_snapshot),
                    exclude_tasks=tuple(session.tasks_snapshot),
                )
                session.current_index = len(session.tasks_snapshot)
                session.tasks_snapshot = [
                    *session.tasks_snapshot, *(task.model_dump(mode="json") for task in selected)
                ]
                session.notice = notice
                session.draft_revision += 1
                mark_seen(self, db, session.guest_id, selected)
                db.flush()
                return session_view(session, attempts)

            return self._idempotent(
                db, guest, key, f"POST /sessions/{session.id}/extend", body, append,
            )

    def get_session(self, token: str | None, session_id: str) -> LearningSession:
        with self._guest_transaction(token) as (db, guest):
            session = self._owned(db, guest, session_id)
            return session_view(session, self._attempts(db, session.id))

    def draft(self, token: str | None, session_id: str, request: DraftRequest) -> DraftRevision:
        with (
            self.observe_save("draft_save") as observation,
            self._guest_transaction(token, write=True) as (db, guest),
        ):
            session = self._owned(db, guest, session_id)
            self._active(session)
            index, _ = self._task(session, request.task_id)
            self._bounded_seconds(request.active_seconds)
            if session.draft_revision != request.expected_revision:
                raise ApiError(
                    409, "draft_conflict",
                    "Черновик уже изменён. Сохраните локальный ввод и обновите сессию."
                )
            observation.attempted = True
            cumulative = self._track_time(session, request.task_id, request.active_seconds)
            session.drafts = {
                **session.drafts,
                request.task_id: {"answer": request.answer, "active_seconds": cumulative},
            }
            session.current_index = index
            session.draft_revision += 1
            observation.success = True
            return DraftRevision(draft_revision=session.draft_revision)

    def attempt(
        self, token: str | None, session_id: str, request: AttemptRequest, key: str | None
    ) -> StoredResponse:
        with (
            self.observe_save("attempt_save") as observation,
            self._guest_transaction(token, write=True) as (db, guest),
        ):
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
                    if request.skipped:
                        result = None
                    else:
                        try:
                            result = check_answer(request.answer, task["answer"])
                        except Exception:
                            self.operation_health.record_event("answer_check", success=False)
                            raise
                        self.operation_health.record_event("answer_check", success=True)
                except AnswerFormatError as exc:
                    raise ApiError(422, exc.code, str(exc), "answer") from exc
                attempts = self._attempts(db, session.id)
                previous = [attempt for attempt in attempts if attempt.task_id == request.task_id]
                owners = self.owner_ids(db, guest)
                aliases = aliases_for_task(db, owners, task)
                seen = next((item for item in aliases.records
                             if item.guest_id == session.guest_id and item.task_id == task["id"]),
                            None)
                if seen is None:
                    raise ApiError(
                        503, "state_unavailable", "Не удалось восстановить историю задачи."
                    )
                assisted = any(item.assistance_seen or item.reference_seen
                               for item in aliases.records)
                prior_numeric = bool(aliases.ids & prior_numeric_ids(db, owners))
                cumulative = self._track_time(session, request.task_id, request.active_seconds)
                record = AttemptRecord(
                    id=str(uuid4()), guest_id=session.guest_id, session_id=session.id,
                    task_id=request.task_id, task_revision=task["revision"], sequence=len(attempts),
                    raw_answer=request.answer,
                    normalized_answer=result.normalized_answer if result else None,
                    correct=result.correct if result else False,
                    assisted=assisted, first_attempt=not previous,
                    independent=(
                        not request.skipped and not previous and not assisted
                        and not prior_numeric
                    ),
                    skipped=request.skipped, active_seconds=cumulative, created_at=self.clock(),
                    checker_revision="fraction-v1",
                    expected_answer=parse_answer(task["answer"], "exam").normalized_answer,
                    solution=task["solution"],
                )
                observation.attempted = True
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

            response = self._idempotent(
                db, guest, key, f"POST /sessions/{session.id}/attempts", request, submit
            )
            observation.success = response.status_code == 200
            return response

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
            aliases = aliases_for_task(db, self.owner_ids(db, guest), task)
            seen = next((item for item in aliases.records
                         if item.guest_id == session.guest_id and item.task_id == task_id), None)
            if seen is None:
                raise ApiError(503, "state_unavailable", "Не удалось восстановить историю задачи.")
            session.help_state = {**session.help_state, task_id: state}
            seen.assistance_seen = True
            if level is None:
                seen.reference_seen = True
            from app.learning.evidence import record_help

            record_help(db, guest, session, task_id, self.clock(), level=level)
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
        owners = self.owner_ids(db, guest)
        sessions = list(
            db.scalars(
                select(LearningSessionRecord).where(LearningSessionRecord.guest_id.in_(owners))
                .order_by(LearningSessionRecord.created_at.desc(), LearningSessionRecord.id.desc())
            )
        )
        attempts = list(
            db.scalars(
                select(AttemptRecord).where(AttemptRecord.guest_id.in_(owners))
                .order_by(
                    AttemptRecord.created_at, AttemptRecord.session_id, AttemptRecord.sequence
                )
            )
        )
        return sessions, attempts

    def progress(self, token: str | None) -> Progress:
        with self._guest_transaction(token) as (db, guest):
            bundle = self.content(db)
            self.reauthorize(db, token, write=False)
            dashboard = self.extras.dashboard_for(db, guest, bundle)
            sessions, attempts = self._history(db, guest)
            snapshots = {
                (session.id, task["id"]): task
                for session in sessions for task in session.tasks_snapshot
            }
            slots = [slot.model_dump(exclude={"skills", "title"}) for slot in dashboard.slots]
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
                independent_total=dashboard.independent_total,
                independent_correct=dashboard.independent_correct,
                assisted_total=dashboard.assisted_total,
                corrections_total=dashboard.corrections_total,
                skipped_total=dashboard.skipped_total,
                algorithm_version=dashboard.algorithm_version,
                notice=dashboard.notice, excluded_total=dashboard.excluded_total,
                active_session_id=next((s.id for s in sessions if s.status == "active"), None),
                slots=slots,
                recent_sessions=[
                    {"id": session.id, "status": session.status,
                     "created_at": session.created_at.isoformat(),
                     "profile": session.profile_snapshot,
                     "summary": summaries[session.id]}
                    for session in sessions[:20]
                ],
                mistakes=mistakes,
            )

    def export(self, token: str | None) -> "HistoryExport":
        from app.history import export_history

        with self._guest_transaction(token) as (db, guest):
            return export_history(self, db, guest, self.clock())
