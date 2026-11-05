"""Bounded, explicit public learning DTOs. No ORM serialization or grading internals."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas import Attempt, Identifier, PublicTask, Schema


class SkillProgress(Schema):
    id: str
    title: str
    attempts: int
    correct: int


class SlotProgress(Schema):
    slot_id: str
    number: int
    title: str
    status: Literal["Нет данных", "Изучаю", "Закрепляю", "Освоено"]
    attempts: int
    correct: int
    covered_skills: int
    total_skills: int
    skills: list[SkillProgress]


class ReviewView(Schema):
    skill_id: str
    family_id: str
    slot_id: str
    slot: int | None
    due_at: str
    interval_days: int
    overdue: bool


class WeakSkill(Schema):
    id: str
    title: str
    slot: int
    family_ids: list[str]


class Favourite(Schema):
    task: PublicTask
    session_id: str
    profile_id: str
    profile_revision: str


Cause = Literal["theory", "model", "calculation", "restriction", "graph", "format"]


class AnnotationRequest(Schema):
    session_id: Annotated[str, Field(min_length=1, max_length=36)]
    task_id: Identifier
    favourite: bool = False
    manual: bool = False
    not_understood: bool = False
    cause: Cause | None = None

    @model_validator(mode="after")
    def has_changes(self) -> "AnnotationRequest":
        if not self.model_fields_set - {"session_id", "task_id"}:
            raise ValueError("Provide at least one annotation field")
        return self


class AnnotationView(Schema):
    id: str
    session_id: str
    task_id: str
    favourite: bool
    manual: bool
    not_understood: bool
    cause: Cause | None
    created_at: str
    updated_at: str


class JournalEntry(Schema):
    id: str
    task: PublicTask
    session_id: str
    profile_id: str
    profile_revision: str
    attempt: Attempt | None
    cause: Cause | None
    manual: bool
    not_understood: bool


class AssessmentSummary(Schema):
    id: str
    mode: Literal["diagnostic", "exam"]
    profile_id: str
    profile_revision: str
    released_at: str
    snapshot_at: str
    score: int
    total: Literal[13]
    answered: int
    skipped: int
    format_errors: int
    active_seconds: int
    elapsed_seconds: int


class Notification(Schema):
    id: str
    message: str
    created_at: str


class Pagination(Schema):
    offset: int
    limit: int
    totals: dict[str, int]


class Plan(Schema):
    minutes: Literal[10, 20, 30]
    length: Literal[5, 10, 20]
    estimated_seconds: int
    slots: list[int]
    selection: Literal["mixed"]
    notice: str | None


class ExportReview(Schema):
    skill_id: str
    family_id: str
    slot_id: str
    due_at: str | None
    interval_days: int
    closed: bool
    anchor_task_id: str
    anchor_at: str


class LearningExport(Schema):
    version: Literal["1"]
    algorithm_version: str
    exported_at: str
    annotations: list[AnnotationView]
    reviews: list[ExportReview]
    pagination: Pagination


class Dashboard(Schema):
    algorithm_version: str
    notice: str | None
    independent_total: int
    independent_correct: int
    assisted_total: int
    corrections_total: int
    skipped_total: int
    excluded_total: int
    slots: list[SlotProgress]
    reviews: list[ReviewView]
    weak_skills: list[WeakSkill]
    favourites: list[Favourite]
    journal: list[JournalEntry]
    assessment_history: list[AssessmentSummary]
    notifications: list[Notification]
    recommendation: str
    pagination: Pagination
