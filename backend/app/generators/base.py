import re
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from app.checker import format_fraction, parse_answer
from app.schemas import ProfileSource


def decimal_text(value: Fraction | int) -> str:
    if isinstance(value, bool) or not isinstance(value, (Fraction, int)):
        raise TypeError("Answers must use exact rational arithmetic")
    result = format_fraction(Fraction(value))
    if "/" in result:
        raise ValueError("A generated answer must have a finite decimal representation")
    return parse_answer(result, "exam").normalized_answer


@dataclass(frozen=True, slots=True)
class Family:
    id: str
    slot: int
    title: str
    skill_ids: tuple[str, ...]
    generate: Callable[[int, ProfileSource], dict[str, Any]]
    supports_runtime: bool = False


def make_task(
    profile: ProfileSource,
    slot: int,
    family_id: str,
    seed: int,
    *,
    title: str,
    statement: str,
    answer: Fraction | int,
    skills: list[str],
    hints: list[str],
    solution: list[str],
    formula: str | None = None,
    table: dict[str, Any] | None = None,
    difficulty: int = 1,
    estimated_seconds: int = 120,
    figure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an unsigned 32-bit integer")
    if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", family_id):
        raise ValueError("Family ID must be a stable lowercase identifier")
    position = next((item for item in profile.slots if item.number == slot), None)
    if position is None:
        raise ValueError("Unknown profile slot")
    if not skills or not set(skills) <= {skill.id for skill in position.skills}:
        raise ValueError("Unknown profile skill")
    if len(set(skills)) != len(skills) or len(hints) != 3:
        raise ValueError("Unique skills and three hints are required")
    if not all(part.strip() for part in [title, statement, *hints, *solution]) or not solution:
        raise ValueError("Task text and explanation cannot be empty")
    return {
        "id": f"course-{family_id}-{seed}", "revision": "1", "slot": slot,
        "slot_id": position.id, "topic": position.title, "title": title,
        "statement": statement, "formula": formula, "table": table, "figure": figure,
        "skill_ids": skills, "family_id": family_id,
        "estimated_seconds": estimated_seconds, "review_status": "demo", "hint_count": 3,
        "answer": decimal_text(answer), "hints": hints, "solution": solution,
        "source": {
            "author": "ИИ-помощник проекта",
            "origin": "Оригинальный материал; независимая предметная рецензия не выполнена.",
            "rights": "Создан для проекта без копирования стороннего банка; права требуют сверки.",
            "reviewed_by": None,
        },
        "profile_id": profile.id, "difficulty": difficulty, "rounding": None,
        "generation": {"template_id": family_id, "template_version": "1", "seed": seed},
    }
