"""Explicit editorial DTOs. Content is JSON data; authority is never a body field."""

from typing import Annotated, Any, Literal

from pydantic import Field, field_validator

from app.content import Task
from app.schemas import Identifier, ProfileSource, PublicTask, Schema

Kind = Literal["task", "lesson", "profile", "template"]
Status = Literal["draft", "review", "ready", "published", "archived"]
Note = Annotated[str, Field(min_length=5, max_length=2000)]
Seed = Annotated[int, Field(ge=0, le=2**32 - 1)]
RevisionNumber = Annotated[int, Field(ge=1)]
Action = Literal[
    "edit",
    "submit",
    "return_to_draft",
    "approve",
    "publish",
    "fork",
    "archive",
    "withdraw",
    "run_checks",
    "review_sample",
]


class EditorActor(Schema):
    id: Identifier
    role: Literal["methodist", "admin"]
    owner_id: Identifier


class CreateRevision(Schema):
    kind: Kind
    payload: dict[str, Any]
    change_note: Note

    @field_validator("change_note")
    @classmethod
    def meaningful_note(cls, value: str) -> str:
        if len(value.strip()) < 5:
            raise ValueError("Опишите изменение минимум пятью символами.")
        return value.strip()


class EditRevision(Schema):
    expected_revision: RevisionNumber
    payload: dict[str, Any]
    change_note: Note


class ChangeRequest(Schema):
    expected_revision: RevisionNumber
    note: Note


class ReviewRequest(ChangeRequest):
    reviewed_formula: bool = False
    reviewed_constraints: bool = False


class BaseImport(Schema):
    change_note: Note


class ImportBatch(Schema):
    version: Literal["1"]
    # Row validation deliberately occurs inside the service, so every error has a row index.
    items: Annotated[list[Any], Field(min_length=1, max_length=10)]


class PublicationRef(Schema):
    id: Identifier
    expected_revision: RevisionNumber


class PublishBatch(Schema):
    items: Annotated[list[PublicationRef], Field(min_length=1, max_length=1000)]
    note: Note


class WithdrawRequest(Schema):
    task_revision: Identifier
    reason: Note


class TemplatePayload(Schema):
    id: Identifier
    title: Annotated[str, Field(min_length=1, max_length=300)]
    generator_id: Identifier
    generator_version: Identifier
    profile_id: Identifier
    profile_revision_id: Identifier | None = None
    slot_id: Identifier
    family_id: Identifier
    skill_ids: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    formula_notes: Annotated[str, Field(min_length=5, max_length=8000)]
    constraints: Annotated[list[Note], Field(min_length=1, max_length=30)]


class SampleReview(ChangeRequest):
    seed: Seed
    output_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    approved: bool


class RevisionSummary(Schema):
    id: str
    kind: Kind
    content_id: str
    content_revision: str
    version: int
    revision: int
    status: Status
    title: str
    author_id: str
    reviewer_id: str | None
    change_note: str
    created_at: str
    updated_at: str
    capabilities: list[Action]


class AuditEvent(Schema):
    id: str
    actor_id: str
    actor_role: str
    action: str
    from_status: str | None
    to_status: str | None
    note: str
    created_at: str


class EvidenceSummary(Schema):
    automated_seeds: int
    automated_passed: bool
    reviewed_seeds: list[int]
    rejected_seeds: list[int]
    checks: list[str]
    failure: str | None


class RevisionView(RevisionSummary):
    payload: dict[str, Any]
    review_note: str | None
    published_at: str | None
    audit: list[AuditEvent]
    evidence: EvidenceSummary | None


class RevisionList(Schema):
    items: list[RevisionSummary]
    total: int
    limit: int
    offset: int


class BatchResult(Schema):
    items: list[RevisionView]


class Preview(Schema):
    kind: Kind
    task: PublicTask | None
    payload: dict[str, Any]
    message: str


class EditorMeta(Schema):
    actor: EditorActor
    profile: ProfileSource
    kinds: list[Kind]
    statuses: list[Status]
    max_import_items: int
    max_request_bytes: int
    templates: list[dict[str, Any]]


class BaseItem(Schema):
    kind: Kind
    content_id: str
    title: str
    content_revision: str


class BaseList(Schema):
    items: list[BaseItem]
    total: int


class Withdrawal(Schema):
    task_id: str
    task_revision: str
    reason: str
    created_at: str
    historical_scores_unchanged: Literal[True] = True


class TemplateSample(Schema):
    seed: int
    output_hash: str
    task: Task


class CheckResult(Schema):
    id: str
    passed: bool
    seed_count: int
    checks: list[str]
    failure: str | None
