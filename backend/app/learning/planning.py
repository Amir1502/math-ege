"""Whole-second, non-punitive time estimates using active solving time only."""

from collections.abc import Sequence
from fractions import Fraction
from math import ceil

from app.content import Task
from app.learning.policy import LearningProjection


def _median(values: list[int]) -> Fraction:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return Fraction(ordered[middle]) if len(ordered) % 2 else Fraction(
        ordered[middle - 1] + ordered[middle], 2,
    )


def _personal_seconds(projection: LearningProjection) -> Fraction | None:
    policy = projection.policy
    values = [item.active_seconds for item in projection.evidence
              if item.independent and item.active_seconds > 0][-policy.duration_window:]
    return _median(values) if len(values) >= policy.duration_min_samples else None


def estimate_seconds(tasks: Sequence[Task], projection: LearningProjection) -> int:
    personal = _personal_seconds(projection)
    return (ceil(personal * len(tasks)) if personal is not None
            else sum(task.estimated_seconds for task in tasks))


def plan_length(minutes: int, tasks: Sequence[Task], projection: LearningProjection) -> int:
    if minutes not in {10, 20, 30}:
        raise ValueError("Plans support 10, 20 or 30 minutes")
    seconds = _personal_seconds(projection)
    if seconds is None:
        seconds = _median([task.estimated_seconds for task in tasks]) if tasks else Fraction(
            projection.policy.fallback_seconds,
        )
    allowed = [length for length in projection.policy.session_lengths
               if seconds * length <= minutes * 60]
    return max(allowed) if allowed else min(projection.policy.session_lengths)
