from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.models import AssessmentRecord
from app.models import AttemptRecord


def prior_numeric_ids(
    db: Session, owners: list[str], *, at: datetime | None = None,
    exclude_assessment_id: str | None = None,
) -> set[str]:
    attempts = select(AttemptRecord.task_id).where(
        AttemptRecord.guest_id.in_(owners), AttemptRecord.skipped.is_(False),
        AttemptRecord.normalized_answer.is_not(None),
    )
    if at is not None:
        attempts = attempts.where(AttemptRecord.created_at <= at)
    identifiers = set(db.scalars(attempts))
    assessments = select(AssessmentRecord).where(
        AssessmentRecord.guest_id.in_(owners), AssessmentRecord.server_result.is_not(None),
    )
    if exclude_assessment_id is not None:
        assessments = assessments.where(AssessmentRecord.id != exclude_assessment_id)
    for record in db.scalars(assessments):
        result = record.server_result
        if result["source"] != "server" or (
            at is not None and datetime.fromisoformat(result["snapshot_at"]) > at
        ):
            continue
        identifiers.update(row["task_id"] for row in result["rows"]
                           if row["normalized"] is not None)
    return identifiers
