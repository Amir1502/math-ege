from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Account, AccountConsent, AccountDeletionRequest
from app.accounts.schemas import ConsentView, DeletionView
from app.assessments.models import AssessmentRecord
from app.assessments.presentation import assessment_view
from app.assessments.schemas import AssessmentMode, AssessmentResult, DraftAnswer
from app.learning.annotations import annotation_view, annotations_for
from app.learning.evidence import editorial_exclusions, editorial_notices, load_history
from app.learning.policy import replay
from app.learning.schemas import AnnotationView, ExportReview
from app.models import Guest
from app.presentation import session_view
from app.schemas import Export, ProfileSource, PublicTask, Schema

if TYPE_CHECKING:
    from app.services import LearningService


class ExportAccount(Schema):
    id: str
    email: str
    created_at: str
    email_verified_at: str
    role: Literal["student", "methodist", "admin"]
    daily_minutes: Literal[10, 20, 30]
    consents: list[ConsentView]
    deletion_request: DeletionView | None


class ExportAssessment(Schema):
    id: str
    mode: AssessmentMode
    status: Literal["prepared", "active", "awaiting_snapshot", "completed"]
    profile_id: str
    profile_revision: str
    profile: ProfileSource
    created_at: str
    started_at: str | None
    deadline_at: str | None
    released_at: str | None
    duration_minutes: int
    tasks: list[PublicTask]
    drafts: dict[str, DraftAnswer]
    server_result: AssessmentResult | None
    local_result: AssessmentResult | None
    result_notice: str


class ExportCorrection(Schema):
    task_id: str
    task_revision: str
    reason: str
    created_at: str
    attempt_ids: list[str]
    session_ids: list[str]
    assessment_ids: list[str]


class ExportLearning(Schema):
    algorithm_version: str
    annotations: list[AnnotationView]
    reviews: list[ExportReview]
    corrections: list[ExportCorrection]


class HistoryExport(Export):
    assessments: list[ExportAssessment]
    learning: ExportLearning
    account: ExportAccount | None


def account_data(db: Session, guest: Guest) -> ExportAccount | None:
    account = db.scalar(select(Account).where(Account.root_guest_id == guest.id))
    if account is None:
        return None
    consents = db.scalars(select(AccountConsent).where(
        AccountConsent.account_id == account.id,
    ).order_by(AccountConsent.accepted_at, AccountConsent.id))
    deletion = db.scalar(select(AccountDeletionRequest).where(
        AccountDeletionRequest.account_id == account.id,
    ))
    return ExportAccount(
        id=account.id, email=account.email, created_at=account.created_at.isoformat(),
        email_verified_at=account.email_verified_at.isoformat(), role=account.role,
        daily_minutes=account.daily_minutes,
        consents=[ConsentView(policy_version=row.policy_version,
                              accepted_at=row.accepted_at.isoformat()) for row in consents],
        deletion_request=DeletionView(
            id=deletion.id, status=deletion.status, requested_at=deletion.requested_at.isoformat(),
            deadline_at=deletion.deadline_at.isoformat(),
        ) if deletion is not None else None,
    )


def export_history(
    learning: "LearningService", db: Session, guest: Guest, now: datetime,
) -> HistoryExport:
    owners = learning.owner_ids(db, guest)
    sessions, attempts = learning._history(db, guest)
    history = load_history(db, owners, practice=(sessions, attempts))
    projection = replay(history.events, learning.extras.policy, exclusions=editorial_exclusions(db))
    attempts_by_session = defaultdict(list)
    for attempt in attempts:
        attempts_by_session[attempt.session_id].append(attempt)
    assessments = [ExportAssessment.model_validate(
        assessment_view(record, now, None).model_dump(include=set(ExportAssessment.model_fields)),
    ) for record in db.scalars(select(AssessmentRecord).where(
        AssessmentRecord.guest_id.in_(owners),
    ).order_by(AssessmentRecord.created_at, AssessmentRecord.id))]
    return HistoryExport(
        version="1", exported_at=now.isoformat(), profile_id=learning.content(db).profile.id,
        sessions=[session_view(session, attempts_by_session[session.id]) for session in sessions],
        assessments=assessments, account=account_data(db, guest),
        learning=ExportLearning(
            algorithm_version=projection.policy.version,
            annotations=[
                annotation_view(row) for row in annotations_for(db, owners, history).values()
            ],
            reviews=[ExportReview(
                skill_id=row.skill_id, family_id=row.family_id, slot_id=row.slot_id,
                due_at=row.due_at.isoformat() if row.due_at else None,
                interval_days=row.interval_days, closed=row.due_at is None,
                anchor_task_id=row.anchor_task_id, anchor_at=row.anchor_at.isoformat(),
            ) for row in projection.reviews],
            corrections=[ExportCorrection.model_validate({
                field: row[field] for field in ExportCorrection.model_fields
            }) for row in editorial_notices(db, owners)],
        ),
    )
