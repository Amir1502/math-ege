"""The snake_case HTTP contract. Public task fields are an explicit allowlist."""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    TypeAdapter,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
AnswerText = Annotated[str, Field(max_length=64)]
ActiveSeconds = Annotated[int, Field(ge=0, le=86_400)]
StrictInteger = BeforeValidator(TypeAdapter(StrictInt).validate_python)


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorDetail(Schema):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(Schema):
    error: ErrorDetail


class Skill(Schema):
    id: Identifier
    title: str


class SlotSource(Schema):
    number: Annotated[int, Field(ge=1)]
    id: Identifier
    title: str
    level: Literal["Б", "П"]
    summary: str
    skills: Annotated[list[Skill], Field(min_length=1)]
    lesson_id: Identifier


class Slot(SlotSource):
    available_tasks: int


class ProfileSource(Schema):
    id: Identifier
    year: int
    title: str
    status: Literal["draft"]
    revision: Identifier
    verified_at: str
    verification_note: str
    source_urls: list[str]
    slots: Annotated[list[SlotSource], Field(min_length=1)]


class Profile(Schema):
    id: Identifier
    year: int
    title: str
    status: Literal["draft"]
    revision: Identifier
    verified_at: str
    verification_note: str
    source_urls: list[str]
    demo_mode: bool
    bank_size: int
    slots: list[Slot]


class LessonSection(Schema):
    heading: str
    body: str
    formula: str | None


class WorkedExample(Schema):
    statement: str
    steps: Annotated[list[str], Field(min_length=1)]
    answer: str


class Lesson(Schema):
    id: Identifier
    title: str
    slot: int
    minutes: Annotated[int, Field(ge=1)]
    skill_ids: Annotated[list[Identifier], Field(min_length=1)]
    sections: Annotated[list[LessonSection], Field(min_length=1)]
    example: WorkedExample
    takeaway: str


class TaskTable(Schema):
    headers: Annotated[list[str], Field(min_length=1)]
    rows: Annotated[list[list[str]], Field(min_length=1)]

    @model_validator(mode="after")
    def rectangular(self) -> "TaskTable":
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError("Table rows must match the header width")
        return self


class PublicTask(Schema):
    id: Identifier
    revision: Identifier
    slot: int
    topic: str
    title: str
    statement: str
    formula: str | None
    table: TaskTable | None
    skill_ids: Annotated[list[Identifier], Field(min_length=1)]
    family_id: Identifier
    estimated_seconds: Annotated[int, Field(ge=1, le=86_400)]
    review_status: Literal["demo"]
    hint_count: Annotated[int, Field(ge=0, le=3)]


class EmptyRequest(Schema):
    pass


class CreateSessionRequest(Schema):
    slots: Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=1, max_length=100)]
    length: Annotated[Literal[5, 10, 20], StrictInteger]
    mode: Literal["practice"]

    @field_validator("slots")
    @classmethod
    def unique_slots(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Позиции должны быть уникальными.")
        return value


class DraftRequest(Schema):
    task_id: Identifier
    answer: AnswerText
    active_seconds: ActiveSeconds
    expected_revision: Annotated[int, Field(ge=0)]


class AttemptRequest(Schema):
    task_id: Identifier
    answer: AnswerText
    active_seconds: ActiveSeconds
    skipped: bool


class HintRequest(Schema):
    task_id: Identifier
    level: Annotated[Literal[1, 2, 3], StrictInteger]


class SolutionRequest(Schema):
    task_id: Identifier


class Hint(Schema):
    level: int
    text: str


class Solution(Schema):
    answer: str
    steps: list[str]


class HelpState(Schema):
    hints: list[Hint]
    solution: Solution | None


class Draft(Schema):
    answer: str
    active_seconds: int


class DraftRevision(Schema):
    draft_revision: int


class Attempt(Schema):
    id: str
    task_id: str
    raw_answer: str
    normalized_answer: str | None
    correct: bool
    assisted: bool
    first_attempt: bool
    independent: bool
    skipped: bool
    active_seconds: int
    created_at: str
    expected_answer: str
    solution: list[str]


class Summary(Schema):
    total: int
    answered: int
    independent_total: int
    independent_correct: int
    assisted: int
    corrections: int
    skipped: int
    active_seconds: int


class LearningSession(Schema):
    id: str
    profile_id: str
    mode: Literal["practice"]
    status: Literal["active", "completed"]
    created_at: str
    completed_at: str | None
    current_index: int
    requested_length: int
    notice: str | None
    draft_revision: int
    tasks: list[PublicTask]
    attempts: list[Attempt]
    drafts: dict[str, Draft]
    help: dict[str, HelpState]
    summary: Summary


class SlotProgress(Schema):
    number: int
    attempts: int
    correct: int
    status: Literal["Нет данных", "Изучаю", "Закрепляю"]
    covered_skills: int
    total_skills: int


class RecentSession(Schema):
    id: str
    status: Literal["active", "completed"]
    created_at: str
    summary: Summary


class Mistake(Schema):
    task: PublicTask
    attempt: Attempt


class Progress(Schema):
    independent_total: int
    independent_correct: int
    assisted_total: int
    corrections_total: int
    skipped_total: int
    active_session_id: str | None
    slots: list[SlotProgress]
    recent_sessions: list[RecentSession]
    mistakes: list[Mistake]


class Export(Schema):
    version: Literal["1"]
    exported_at: str
    profile_id: str
    sessions: list[LearningSession]


class GuestResponse(Schema):
    id: str


class HealthResponse(Schema):
    status: Literal["ok"]
