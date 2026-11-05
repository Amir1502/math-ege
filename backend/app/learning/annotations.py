"""Owned annotation mutations and safe journal/favourite projections."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learning.evidence import History, TaskContext, record_signal
from app.learning.models import TaskAnnotation
from app.learning.schemas import (
    AnnotationRequest,
    AnnotationView,
    Favourite,
    JournalEntry,
)
from app.schemas import Schema


class AnnotationMutation(Schema):
    """Canonical body for core idempotency: omitted values stay omitted."""

    session_id: str
    task_id: str
    changes: dict[str, bool | str | None]


def mutation(request: AnnotationRequest) -> AnnotationMutation:
    return AnnotationMutation(
        session_id=request.session_id, task_id=request.task_id,
        changes=request.model_dump(exclude_unset=True, exclude={"session_id", "task_id"}),
    )


def annotation_view(row: TaskAnnotation) -> AnnotationView:
    return AnnotationView(
        id=row.id, session_id=row.session_id, task_id=row.task_id,
        favourite=row.favourite, manual=row.manual, not_understood=row.not_understood,
        cause=row.cause, created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def save_annotation(
    db: Session, context: TaskContext, request: AnnotationRequest, now: datetime,
) -> AnnotationView:
    row = db.scalar(select(TaskAnnotation).where(
        TaskAnnotation.session_id == context.session_id, TaskAnnotation.task_id == context.task.id,
    ))
    if row is None:
        row = TaskAnnotation(
            id=str(uuid4()), owner_id=context.owner_id, session_id=context.session_id,
            task_id=context.task.id, source=context.source, favourite=False, manual=False,
            not_understood=False, cause=None, created_at=now, updated_at=now,
        )
        db.add(row)
    was_not_understood = row.not_understood
    for name, value in mutation(request).changes.items():
        setattr(row, name, value)
    row.updated_at = now
    if row.not_understood and not was_not_understood:
        record_signal(db, context, f"not-understood:{uuid4()}", now, source="not_understood")
    db.flush()
    return annotation_view(row)


def annotations_for(
    db: Session, owners: list[str], history: History,
) -> dict[tuple[str, str], TaskAnnotation]:
    return {(row.session_id, row.task_id): row for row in db.scalars(select(TaskAnnotation).where(
        TaskAnnotation.owner_id.in_(owners),
    ).order_by(TaskAnnotation.updated_at.desc(), TaskAnnotation.id))
            if (row.session_id, row.task_id) in history.tasks}


def journal_and_favourites(
    history: History, annotations: dict[tuple[str, str], TaskAnnotation],
) -> tuple[list[JournalEntry], list[Favourite]]:
    entries = []
    automatic = set()
    for identifier, attempt in sorted(
        history.attempts.items(), key=lambda item: (item[1].created_at, item[0]), reverse=True,
    ):
        if not (attempt.skipped or (attempt.first_attempt and not attempt.correct)):
            continue
        context = history.event_tasks[identifier]
        key = (context.session_id, attempt.task_id)
        automatic.add(key)
        row = annotations.get(key)
        entries.append(JournalEntry(
            id=attempt.id, task=context.task, session_id=context.session_id, attempt=attempt,
            profile_id=context.profile_id, profile_revision=context.profile_revision,
            cause=row.cause if row else None, manual=row.manual if row else False,
            not_understood=row.not_understood if row else False,
        ))
    favourites = []
    for key, row in annotations.items():
        context = history.tasks[key]
        if row.favourite:
            favourites.append(Favourite(
                task=context.task, session_id=context.session_id,
                profile_id=context.profile_id, profile_revision=context.profile_revision,
            ))
        if key in automatic or not (row.manual or row.not_understood):
            continue
        attempts = [item for identifier, item in history.attempts.items()
                    if history.event_tasks[identifier].session_id == row.session_id
                    and item.task_id == row.task_id]
        attempt = min(attempts, key=lambda item: (not item.first_attempt, item.created_at, item.id),
                      default=None)
        entries.append(JournalEntry(
            id=row.id, task=context.task, session_id=context.session_id, attempt=attempt,
            profile_id=context.profile_id, profile_revision=context.profile_revision,
            cause=row.cause, manual=row.manual, not_understood=row.not_understood,
        ))
    return entries, favourites
