"""Public read adapter for learning projections; local results are never evidence."""

from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.models import AssessmentRecord


def released_evidence(db: Session, guest_ids: list[str]) -> list[dict[str, Any]]:
    """Return detached canonical rows only after explicit finish acceptance.

    Callers supply authenticated owner origins and retain immutable event IDs.
    They must deduplicate instances across practice and merged guest histories,
    and exclude format_error rows from numeric accuracy/mastery denominators.
    """
    records = db.scalars(select(AssessmentRecord).where(
        AssessmentRecord.guest_id.in_(guest_ids),
        AssessmentRecord.status == "completed",
        AssessmentRecord.released_at.is_not(None),
        AssessmentRecord.server_result.is_not(None),
    ).order_by(AssessmentRecord.created_at, AssessmentRecord.id))
    evidence = []
    for record in records:
        result = record.server_result
        tasks = {task["id"]: task for task in record.tasks_snapshot}
        for sequence, row in enumerate(result["rows"]):
            evidence.append({
                **deepcopy(row),
                "assessment_id": record.id,
                "guest_id": record.guest_id,
                "sequence": sequence,
                "mode": record.mode,
                "source": "assessment",
                "result_source": "server",
                "at": datetime.fromisoformat(result["snapshot_at"]),
                "released_at": record.released_at,
                "checker_revision": result["checker_revision"],
                "profile_id": record.profile_id,
                "profile_revision": record.profile_revision,
                "profile_snapshot": deepcopy(record.profile_snapshot),
                "task_snapshot": deepcopy(tasks[row["task_id"]]),
            })
    return evidence
