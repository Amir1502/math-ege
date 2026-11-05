"""Strict, separate assessment DTOs; input drafts are not numerical attempts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.schemas import ActiveSeconds, AnswerText, Identifier, ProfileSource, PublicTask, Schema

DeviceId = Annotated[UUID, Field(strict=False)]
Generation = Annotated[int, Field(ge=1)]
AssessmentMode = Literal["diagnostic", "exam"]


class PrepareRequest(Schema):
    mode: AssessmentMode
    duration_minutes: Annotated[int, Field(ge=15, le=180)] = 65
    device_id: DeviceId


class WriterRequest(Schema):
    device_id: DeviceId
    writer_generation: Generation


class DraftAnswer(Schema):
    answer: AnswerText
    active_seconds: ActiveSeconds


AnswerMap = Annotated[dict[Identifier, DraftAnswer], Field(max_length=13)]


class DraftRequest(WriterRequest):
    expected_revision: Annotated[int, Field(ge=0)]
    current_index: Annotated[int, Field(ge=0, le=12)]
    answers: AnswerMap


class FinishRequest(WriterRequest):
    answers: AnswerMap
    connection_lost: bool


class FirstDraft(DraftAnswer):
    recorded_at: str


class ResultRow(Schema):
    id: str
    task_id: str
    task_revision: str
    slot: int
    slot_id: str
    family_id: str
    skill_ids: list[str]
    raw: str
    normalized: str | None
    expected: str
    correct: bool
    skipped: bool
    format_error: bool
    format_message: str | None
    independent: bool
    assisted: bool
    first_attempt: bool
    active_seconds: int
    solution: list[str]
    first_draft: FirstDraft | None
    first_answer: FirstDraft | None
    label: Literal["Верно", "Неверно", "Пропущено", "Ошибка формата"]


class AssessmentResult(Schema):
    source: Literal["server", "local"]
    reason: Literal["finished", "deadline", "connection_lost"]
    label: str
    score: Annotated[int, Field(ge=0, le=13)]
    total: Literal[13]
    answered: int
    skipped: int
    format_errors: int
    independent_total: int
    independent_correct: int
    assisted_total: int
    active_seconds: int
    elapsed_seconds: int
    snapshot_at: str
    snapshot_hash: str
    connection_lost: bool
    checker_revision: str
    rows: Annotated[list[ResultRow], Field(min_length=13, max_length=13)]
    weak_skill_ids: list[str]
    recommendation: str


class AssessmentView(Schema):
    id: str
    mode: AssessmentMode
    status: Literal["prepared", "active", "awaiting_snapshot", "completed"]
    profile_id: str
    profile_revision: str
    profile: ProfileSource
    created_at: str
    server_now: str
    started_at: str | None
    deadline_at: str | None
    released_at: str | None
    duration_minutes: int
    writer_generation: int
    can_write: bool
    draft_revision: int
    current_index: int
    tasks: Annotated[list[PublicTask], Field(min_length=13, max_length=13)]
    drafts: dict[str, DraftAnswer]
    server_result: AssessmentResult | None
    local_result: AssessmentResult | None
    result_notice: str
