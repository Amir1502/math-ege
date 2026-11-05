"""Adapters from frozen public history to answer-free, immutable policy evidence."""

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.models import AssessmentRecord
from app.content import public_task
from app.errors import ApiError, not_found
from app.instances import instance_key
from app.learning.models import EvidenceRecord
from app.learning.policy import Evidence
from app.learning.schemas import AssessmentSummary
from app.models import AttemptRecord, Guest, LearningSessionRecord
from app.presentation import attempt_view
from app.schemas import Attempt, PublicTask

# Import the optional read adapter before test schema creation, so its SQLAlchemy
# tables are registered too. A missing subsystem is allowed during isolated work;
# errors inside an installed adapter must still fail rather than hide exclusions.
try:
    from app.editor import repository as _editor_repository
except ModuleNotFoundError as exc:
    if exc.name not in {"app.editor", "app.editor.repository"}:
        raise
    _editor_repository = None


def stable_slot_id(task: dict[str, Any], profile: dict[str, Any]) -> str:
    """Legacy numbers are meaningful only inside their original frozen profile."""
    if task.get("slot_id"):
        return task["slot_id"]
    slot = next((item for item in profile["slots"] if item["number"] == task["slot"]), None)
    if slot is None:
        raise ApiError(
            503, "history_unavailable", "Не удалось восстановить исходную позицию задачи.",
        )
    return slot["id"]


@dataclass(frozen=True, slots=True)
class TaskContext:
    owner_id: str
    session_id: str
    source: str
    task: PublicTask
    profile_id: str
    profile_revision: str
    instance_id: str | None = None


@dataclass(slots=True)
class History:
    events: list[Evidence] = field(default_factory=list)
    tasks: dict[tuple[str, str], TaskContext] = field(default_factory=dict)
    event_tasks: dict[str, TaskContext] = field(default_factory=dict)
    attempts: dict[str, Attempt] = field(default_factory=dict)
    assessments: list[AssessmentSummary] = field(default_factory=list)


def _contexts(
    history: History, record: LearningSessionRecord | AssessmentRecord, source: str,
) -> None:
    for snapshot in record.tasks_snapshot:
        task = public_task(snapshot).model_copy(update={
            "slot_id": stable_slot_id(snapshot, record.profile_snapshot),
        })
        history.tasks[(record.id, task.id)] = TaskContext(
            record.guest_id, record.id, source, task, record.profile_id, record.profile_revision,
            instance_id=instance_key(snapshot),
        )


def _event(identifier: str, context: TaskContext, at: datetime, attempt: Attempt) -> Evidence:
    task = context.task
    return Evidence(
        identifier, task.id, task.revision, tuple(task.skill_ids), task.family_id, task.slot_id,
        at, attempt.correct, attempt.independent, attempt.assisted, attempt.skipped,
        attempt.active_seconds, context.source,
        instance_id=context.instance_id,
    )


def owned_task(db: Session, owners: list[str], session_id: str, task_id: str) -> TaskContext:
    practice = db.scalar(select(LearningSessionRecord).where(
        LearningSessionRecord.id == session_id, LearningSessionRecord.guest_id.in_(owners),
    ))
    history = History()
    if practice is not None:
        _contexts(history, practice, "practice")
    else:
        assessment = db.scalar(select(AssessmentRecord).where(
            AssessmentRecord.id == session_id, AssessmentRecord.guest_id.in_(owners),
            AssessmentRecord.status == "completed", AssessmentRecord.released_at.is_not(None),
            AssessmentRecord.server_result.is_not(None),
        ))
        if assessment is not None and assessment.server_result.get("source") == "server":
            _contexts(history, assessment, "assessment")
    context = history.tasks.get((session_id, task_id))
    if context is None:
        raise not_found()
    return context


def record_signal(
    db: Session, context: TaskContext, identifier: str, now: datetime, *, source: str,
) -> None:
    if db.get(EvidenceRecord, identifier) is not None:
        return
    task = context.task
    event = Evidence(
        identifier, task.id, task.revision, tuple(task.skill_ids), task.family_id, task.slot_id,
        now, False, False, source == "help", False, 0, source,
        instance_id=context.instance_id,
    )
    db.add(EvidenceRecord(
        event_id=identifier, owner_id=context.owner_id, session_id=context.session_id,
        source=source, payload=evidence_payload(event), created_at=now, recorded_at=now,
    ))


def record_help(
    db: Session, guest: Guest, session: LearningSessionRecord, task_id: str, now: datetime,
    *, level: int | None,
) -> None:
    """Core hook inside its authorized owner-locked help mutation; no new transaction."""
    if level not in {None, 1, 2, 3}:
        raise ValueError("Unknown hint level")
    history = History()
    _contexts(history, session, "practice")
    context = history.tasks.get((session.id, task_id))
    if context is None:
        raise not_found()
    identifier = f"help:{uuid5(NAMESPACE_URL, f'{session.id}:{task_id}:{level}')}"
    record_signal(db, context, identifier, now, source="help")


def load_history(
    db: Session, owners: list[str],
    *, practice: tuple[list[LearningSessionRecord], list[AttemptRecord]] | None = None,
) -> History:
    history = History()
    if practice is None:
        practice = (
            list(db.scalars(select(LearningSessionRecord).where(
                LearningSessionRecord.guest_id.in_(owners),
            ))),
            list(db.scalars(select(AttemptRecord).where(AttemptRecord.guest_id.in_(owners)))),
        )
    sessions, attempts = practice
    for session in sessions:
        _contexts(history, session, "practice")
    for record in attempts:
        context = history.tasks[(record.session_id, record.task_id)]
        identifier = f"practice:{record.id}"
        attempt = attempt_view(record)
        history.events.append(_event(identifier, context, record.created_at, attempt))
        history.event_tasks[identifier] = context
        history.attempts[identifier] = attempt
    _released_assessments(db, owners, history)
    for record in db.scalars(select(EvidenceRecord).where(
        EvidenceRecord.owner_id.in_(owners), EvidenceRecord.source.in_(["help", "not_understood"]),
    )):
        event = evidence_from_payload(record.payload)
        context = history.tasks.get((record.session_id, event.task_id))
        # Auxiliary evidence for assessments is gated by the same release query.
        if context is not None:
            if "instance_id" in record.payload and event.instance_id != context.instance_id:
                raise ApiError(503, "evidence_conflict", "Исходное учебное событие изменилось.")
            history.events.append(replace(event, instance_id=context.instance_id))
            history.event_tasks[event.id] = context
    return history


def _released_assessments(db: Session, owners: list[str], history: History) -> None:
    records = db.scalars(select(AssessmentRecord).where(
        AssessmentRecord.guest_id.in_(owners), AssessmentRecord.status == "completed",
        AssessmentRecord.released_at.is_not(None), AssessmentRecord.server_result.is_not(None),
    ).order_by(AssessmentRecord.released_at.desc(), AssessmentRecord.id))
    for record in records:
        result = record.server_result
        if result.get("source") != "server":
            continue
        _contexts(history, record, "assessment")
        at = datetime.fromisoformat(result["snapshot_at"])
        for row in result["rows"]:
            context = history.tasks[(record.id, row["task_id"])]
            identifier = f"assessment:{row['id']}"
            attempt = Attempt(
                id=row["id"], task_id=row["task_id"], raw_answer=row["raw"],
                normalized_answer=row["normalized"], correct=row["correct"],
                assisted=row["assisted"], first_attempt=row["first_attempt"],
                independent=row["independent"], skipped=row["skipped"],
                active_seconds=row["active_seconds"], created_at=at.isoformat(),
                expected_answer=row["expected"], solution=row["solution"],
            )
            history.events.append(_event(identifier, context, at, attempt))
            history.event_tasks[identifier] = context
            history.attempts[identifier] = attempt
        history.assessments.append(AssessmentSummary(
            id=record.id, mode=record.mode, profile_id=record.profile_id,
            profile_revision=record.profile_revision, released_at=record.released_at.isoformat(),
            **{name: result[name] for name in (
                "snapshot_at", "score", "total", "answered", "skipped", "format_errors",
                "active_seconds", "elapsed_seconds",
            )},
        ))


def evidence_payload(event: Evidence) -> dict[str, Any]:
    return {**asdict(event), "at": event.at.isoformat(), "skill_ids": list(event.skill_ids)}


def evidence_from_payload(payload: dict[str, Any]) -> Evidence:
    return Evidence(**{**payload, "at": datetime.fromisoformat(payload["at"])})


def persist_history(db: Session, owners: list[str], history: History, now: datetime) -> None:
    """Read-through exactly-once ledger, under the caller's canonical owner lock."""
    stored = {item.event_id: item for item in db.scalars(
        select(EvidenceRecord).where(EvidenceRecord.owner_id.in_(owners)),
    )}
    for event in history.events:
        context = history.event_tasks[event.id]
        payload = evidence_payload(event)
        previous = stored.get(event.id)
        if previous is not None:
            # Compare a detached copy only: legacy ledger JSON must stay byte/value intact.
            previous_payload = previous.payload
            if "instance_id" not in previous_payload:
                previous_payload = {**previous_payload, "instance_id": context.instance_id}
            if previous_payload != payload:
                raise ApiError(503, "evidence_conflict", "Исходное учебное событие изменилось.")
            continue
        record = EvidenceRecord(
            event_id=event.id, owner_id=context.owner_id, session_id=context.session_id,
            source=event.source, payload=payload, created_at=event.at, recorded_at=now,
        )
        db.add(record)
        stored[event.id] = record


def editorial_exclusions(db: Session) -> dict[tuple[str, str], str]:
    return _editor_repository.exclusions(db) if _editor_repository is not None else {}


def editorial_notices(db: Session, owners: list[str]) -> list[dict[str, Any]]:
    return _editor_repository.notices(db, owners) if _editor_repository is not None else []
