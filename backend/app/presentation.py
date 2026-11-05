"""Public views and cumulative statistics. No mutable ORM object is exposed."""

from collections.abc import Sequence

from app.content import public_task
from app.models import AttemptRecord, LearningSessionRecord
from app.schemas import Attempt, LearningSession, Summary


def attempt_view(attempt: AttemptRecord) -> Attempt:
    return Attempt(
        id=attempt.id,
        task_id=attempt.task_id,
        raw_answer=attempt.raw_answer,
        normalized_answer=attempt.normalized_answer,
        correct=attempt.correct,
        assisted=attempt.assisted,
        first_attempt=attempt.first_attempt,
        independent=attempt.independent,
        skipped=attempt.skipped,
        active_seconds=attempt.active_seconds,
        created_at=attempt.created_at.isoformat(),
        expected_answer=attempt.expected_answer,
        solution=attempt.solution,
    )


def summary_view(session: LearningSessionRecord, attempts: Sequence[AttemptRecord]) -> Summary:
    if session.summary_snapshot is not None:
        return Summary.model_validate(session.summary_snapshot)
    return Summary(
        total=len(session.tasks_snapshot),
        answered=len({attempt.task_id for attempt in attempts if not attempt.skipped}),
        independent_total=sum(attempt.independent for attempt in attempts),
        independent_correct=sum(attempt.independent and attempt.correct for attempt in attempts),
        assisted=sum(attempt.assisted and not attempt.skipped for attempt in attempts),
        corrections=sum(not attempt.first_attempt and not attempt.skipped for attempt in attempts),
        skipped=len({attempt.task_id for attempt in attempts if attempt.skipped}),
        active_seconds=sum(session.active_seconds.values()),
    )


def session_view(
    session: LearningSessionRecord, attempts: Sequence[AttemptRecord]
) -> LearningSession:
    return LearningSession(
        id=session.id,
        profile_id=session.profile_id,
        profile_revision=session.profile_revision,
        profile=session.profile_snapshot,
        mode=session.mode,
        status=session.status,
        created_at=session.created_at.isoformat(),
        completed_at=session.completed_at.isoformat() if session.completed_at else None,
        current_index=session.current_index,
        requested_length=session.requested_length,
        notice=session.notice,
        draft_revision=session.draft_revision,
        tasks=[public_task(task) for task in session.tasks_snapshot],
        attempts=[attempt_view(attempt) for attempt in attempts],
        drafts=session.drafts,
        help=session.help_state,
        summary=summary_view(session, attempts),
        options=session.options_snapshot,
    )
