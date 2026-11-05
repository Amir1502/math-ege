"""Load and validate data-only content. Loading is not permission to issue it."""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import Field, TypeAdapter, model_validator

from app.checker import parse_answer
from app.config import DEFAULT_CONTENT_DIR
from app.markup import MARKUP
from app.schemas import Identifier, Lesson, Profile, ProfileSource, PublicTask, Schema


class ContentError(ValueError):
    """The package failed validation and must not be served."""


class Source(Schema):
    author: str
    origin: str
    rights: str
    reviewed_by: Identifier | None


class Generation(Schema):
    template_id: Identifier
    template_version: Identifier
    seed: Annotated[int, Field(ge=0, le=2**32 - 1)]


class Task(PublicTask):
    answer: Annotated[str, Field(min_length=1, max_length=64)]
    hints: Annotated[list[str], Field(min_length=3, max_length=3)]
    solution: Annotated[list[str], Field(min_length=1)]
    source: Source
    profile_id: Identifier
    difficulty: Annotated[int, Field(ge=1, le=3)]
    generation: Generation | None = None

    @model_validator(mode="after")
    def valid_answer_and_help(self) -> "Task":
        parsed = parse_answer(self.answer, "exam")
        if self.hint_count != len(self.hints):
            raise ValueError("hint_count must match hints")
        if not all(text.strip() for text in [*self.hints, *self.solution]):
            raise ValueError("Hints and solution steps cannot be empty")
        if len(set(self.skill_ids)) != len(self.skill_ids):
            raise ValueError("Task skills must be unique")
        if self.review_status == "reviewed" and (
            not self.source.reviewed_by or self.source.reviewed_by == self.source.author
        ):
            raise ValueError("Reviewed tasks require an independent named reviewer")
        if self.rounding is not None and (
            self.rounding.instruction not in self.statement
            or (parsed.value * 10**self.rounding.digits).denominator != 1
        ):
            raise ValueError("Rounding must be explicit and the reference must match its precision")
        return self


def public_task(task: Task | dict[str, Any]) -> PublicTask:
    """Never serialize the private Task model as a public task."""
    values = task.model_dump() if isinstance(task, Task) else task
    return PublicTask.model_validate({
        name: values[name] for name in PublicTask.model_fields if name in values
    })


@dataclass(frozen=True, slots=True)
class ContentBundle:
    profile: ProfileSource
    lessons: tuple[Lesson, ...]
    tasks: tuple[Task, ...]

    def available_tasks(self, *, allow_demo_content: bool) -> tuple[Task, ...]:
        return tuple(
            task for task in self.tasks if allow_demo_content or task.review_status == "reviewed"
        )

    def public_profile(self, *, allow_demo_content: bool) -> Profile:
        enabled = self.available_tasks(allow_demo_content=allow_demo_content)
        counts = Counter(task.slot for task in enabled)
        values = self.profile.model_dump()
        values["slots"] = [
            {**slot.model_dump(), "available_tasks": counts[slot.number]}
            for slot in self.profile.slots
        ]
        return Profile.model_validate(
            {**values, "demo_mode": any(task.review_status == "demo" for task in enabled),
             "bank_size": len(enabled)}
        )


def _reject_markup(value: Any) -> None:
    if isinstance(value, str) and MARKUP.search(value):
        raise ContentError("HTML and SVG markup are not allowed in the content package")
    if isinstance(value, dict):
        for child in value.values():
            _reject_markup(child)
    elif isinstance(value, list):
        for child in value:
            _reject_markup(child)


def validate_content(profile: Any, lessons: Any, tasks: Any) -> ContentBundle:
    """Validate shape, references, metadata and exact finite expected answers."""
    try:
        _reject_markup([profile, lessons, tasks])
        parsed_profile = ProfileSource.model_validate(profile)
        parsed_lessons = TypeAdapter(list[Lesson]).validate_python(lessons)
        parsed_tasks = TypeAdapter(list[Task]).validate_python(tasks)
        slots = {slot.number: slot for slot in parsed_profile.slots}
        if len(slots) != len(parsed_profile.slots):
            raise ContentError("Profile slot numbers must be unique")
        if len({slot.id for slot in slots.values()}) != len(slots):
            raise ContentError("Profile slot identifiers must be unique")
        for slot in slots.values():
            if len({skill.id for skill in slot.skills}) != len(slot.skills):
                raise ContentError("Skill identifiers within each slot must be unique")
        if len({task.id for task in parsed_tasks}) != len(parsed_tasks):
            raise ContentError("Task identifiers must be unique")
        lesson_by_id = {lesson.id: lesson for lesson in parsed_lessons}
        task_by_id = {task.id: task for task in parsed_tasks}
        families = {task.family_id for task in parsed_tasks}
        if len(lesson_by_id) != len(parsed_lessons):
            raise ContentError("Lesson identifiers must be unique")
        for slot in slots.values():
            lesson = lesson_by_id.get(slot.lesson_id)
            if lesson is None or lesson.kind != "exam" or lesson.slot != slot.number:
                raise ContentError("Every slot must refer to its lesson")
        for item in [*parsed_tasks, *parsed_lessons]:
            if isinstance(item, Lesson) and item.kind == "foundation":
                if item.slot != 0 or item.slot_id is not None or not item.related_slot_ids:
                    raise ContentError("Foundation lessons require related stable slots")
                if not set(item.related_slot_ids) <= {slot.id for slot in slots.values()}:
                    raise ContentError("Foundation lesson refers to an unknown slot")
                continue
            slot = slots.get(item.slot)
            if slot is None:
                raise ContentError("Content refers to an unknown profile slot")
            if not set(item.skill_ids) <= {skill.id for skill in slot.skills}:
                raise ContentError("Content refers to skills outside its profile slot")
            if item.slot_id is not None and item.slot_id != slot.id:
                raise ContentError("Stable slot identity does not match its profile position")
        for lesson in parsed_lessons:
            if not set(lesson.prerequisite_ids) <= lesson_by_id.keys():
                raise ContentError("Lesson refers to an unknown prerequisite")
            if not set(lesson.family_ids) <= families:
                raise ContentError("Lesson refers to an unknown task family")
            for task_id in lesson.practice_task_ids:
                task = task_by_id.get(task_id)
                if task is None or task.slot != lesson.slot:
                    raise ContentError("Lesson practice refers to an unknown or unrelated task")
                if lesson.family_ids and task.family_id not in lesson.family_ids:
                    raise ContentError("Lesson practice refers to an unrelated family")
        visited: set[str] = set()
        visiting: set[str] = set()

        def check_prerequisites(lesson_id: str) -> None:
            if lesson_id in visiting:
                raise ContentError("Lesson prerequisites must not form a cycle")
            if lesson_id in visited:
                return
            visiting.add(lesson_id)
            for prerequisite in lesson_by_id[lesson_id].prerequisite_ids:
                check_prerequisites(prerequisite)
            visiting.remove(lesson_id)
            visited.add(lesson_id)

        for lesson_id in lesson_by_id:
            check_prerequisites(lesson_id)
        for task in parsed_tasks:
            if task.profile_id != parsed_profile.id:
                raise ContentError("Task profile_id does not match the loaded profile")
        for url in parsed_profile.source_urls:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ContentError("Profile source URLs must use HTTP or HTTPS")
        return ContentBundle(parsed_profile, tuple(parsed_lessons), tuple(parsed_tasks))
    except (ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, ContentError):
            raise
        raise ContentError("Invalid content package") from exc


def load_content(content_dir: Path | str | None = None) -> ContentBundle:
    """Read profile.json object, lessons.json array and tasks.json array.

    The default path is absolute and relative to the backend package. The
    caller must still enforce ALLOW_DEMO_CONTENT before issuing demo content.
    """
    directory = Path(content_dir) if content_dir is not None else DEFAULT_CONTENT_DIR
    try:
        values = [
            json.loads((directory / name).read_text(encoding="utf-8"))
            for name in ("profile.json", "lessons.json", "tasks.json")
        ]
    except (OSError, ValueError) as exc:
        raise ContentError("Content package is missing or is not valid JSON") from exc
    return validate_content(*values)
