"""Pure, deterministic learning rules. No database, identity or wall-clock access."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal

REVIEW_INTERVALS = (1, 3, 7, 14, 30)


@dataclass(frozen=True, slots=True)
class LearningPolicy:
    version: str = "learning-v1"
    review_intervals: tuple[int, ...] = REVIEW_INTERVALS
    mastery_attempts: int = 20
    recent_window: int = 10
    recent_correct: int = 8
    mastery_families: int = 3
    mastery_days: int = 2
    retention_days: int = 3
    consolidating_window: int = 5
    consolidating_correct: int = 3
    instance_exclusion_days: int = 30
    selection_weights: tuple[int, int, int] = (5, 3, 2)
    duration_min_samples: int = 5
    duration_window: int = 30
    fallback_seconds: int = 120
    session_lengths: tuple[int, ...] = (5, 10, 20)


DEFAULT_POLICY = LearningPolicy()


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    task_id: str
    task_revision: str
    skill_ids: tuple[str, ...]
    family_id: str
    slot_id: str
    at: datetime
    correct: bool
    independent: bool
    assisted: bool
    skipped: bool
    active_seconds: int
    source: str
    instance_id: str | None = None

    def __post_init__(self) -> None:
        if self.at.tzinfo is None:
            raise ValueError("Evidence requires an aware timestamp")
        object.__setattr__(self, "at", self.at.astimezone(UTC))
        object.__setattr__(self, "skill_ids", tuple(sorted(set(self.skill_ids))))


@dataclass(frozen=True, slots=True)
class Review:
    skill_id: str
    family_id: str
    slot_id: str
    interval_days: int
    due_at: datetime | None
    anchor_task_id: str
    anchor_at: datetime
    last_event_id: str
    anchor_instance_id: str | None = None


@dataclass(frozen=True, slots=True)
class Retention:
    slot_id: str
    skill_id: str
    family_id: str
    at: datetime
    success: bool


@dataclass(frozen=True, slots=True)
class LearningProjection:
    evidence: tuple[Evidence, ...]
    reviews: tuple[Review, ...]
    retention: tuple[Retention, ...]
    policy: LearningPolicy
    excluded_ids: tuple[str, ...] = ()
    encountered_task_ids: tuple[str, ...] = ()
    encountered_instance_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SlotProgress:
    slot_id: str
    status: Literal["Нет данных", "Изучаю", "Закрепляю", "Освоено"]
    attempts: int
    correct: int
    covered_skills: int
    total_skills: int
    families: int
    days: int


def canonical_evidence(events: Iterable[Evidence]) -> tuple[Evidence, ...]:
    """An event is consumed once; a task instance earns independence only once.

    Historic flags are inputs, never rewritten. Deterministic ordering also
    resolves independent attempts made in two guest origins before a merge.
    Revisions do not turn an already exposed instance into a new achievement.
    """
    unique: dict[str, Evidence] = {}
    for event in events:
        if event.id in unique and unique[event.id] != event:
            raise ValueError("Conflicting immutable evidence ID")
        unique[event.id] = event
    seen: set[str] = set()
    result = []
    # With a coarse/injected clock a correction can have the same timestamp as
    # its first answer. The original first-answer flag is the tie-breaker before
    # opaque UUIDs; a correction must never consume that answer's independence.
    for event in sorted(unique.values(), key=lambda item: (item.at, not item.independent, item.id)):
        instance = event.instance_id or event.task_id
        independent = (
            event.independent and not event.assisted and not event.skipped
            and instance not in seen
        )
        result.append(replace(event, independent=independent))
        # A self-reported difficulty resets review but reveals no help or answer.
        if event.source != "not_understood":
            seen.add(instance)
    return tuple(result)


def replay(
    events: Iterable[Evidence], policy: LearningPolicy = DEFAULT_POLICY,
    *, exclusions: Mapping[tuple[str, str], str] | None = None,
) -> LearningProjection:
    canonical = canonical_evidence(events)
    excluded = exclusions or {}
    evidence = tuple(item for item in canonical
                     if (item.task_id, item.task_revision) not in excluded)
    reviews: dict[tuple[str, str], Review] = {}
    last_practice: dict[tuple[str, str], datetime] = {}
    retention = []
    for event in evidence:
        for skill_id in event.skill_ids:
            key = (skill_id, event.family_id)
            current = reviews.get(key)
            gap = event.at - last_practice.get(key, event.at)
            due = current is not None and current.due_at is not None and event.at >= current.due_at
            if not event.correct or event.assisted or event.skipped:
                # A retention-length break can end before a longer scheduled interval.
                if due or gap >= timedelta(days=policy.retention_days) or (
                    current is not None and current.due_at is None
                    and gap >= timedelta(days=policy.review_intervals[0])
                ):
                    retention.append(Retention(
                        event.slot_id, skill_id, event.family_id, event.at, False,
                    ))
                interval = policy.review_intervals[0]
                reviews[key] = Review(
                    skill_id, event.family_id, event.slot_id, interval,
                    event.at + timedelta(days=interval), event.task_id, event.at, event.id,
                    anchor_instance_id=event.instance_id,
                )
            elif (
                due and event.independent
                and (event.instance_id or event.task_id)
                != (current.anchor_instance_id or current.anchor_task_id)
            ):
                index = policy.review_intervals.index(current.interval_days) + 1
                closed = index == len(policy.review_intervals)
                interval = current.interval_days if closed else policy.review_intervals[index]
                reviews[key] = Review(
                    skill_id, event.family_id, event.slot_id, interval,
                    None if closed else event.at + timedelta(days=interval),
                    event.task_id, event.at, event.id,
                    anchor_instance_id=event.instance_id,
                )
                if gap >= timedelta(days=policy.retention_days):
                    retention.append(Retention(
                        event.slot_id, skill_id, event.family_id, event.at, True,
                    ))
            elif (
                current is None and event.independent
                and gap >= timedelta(days=policy.retention_days)
            ):
                # A delayed check of an already-correct family can prove retention
                # too; the learner need not make an error to open a review first.
                retention.append(Retention(
                    event.slot_id, skill_id, event.family_id, event.at, True,
                ))
            last_practice[key] = event.at
    return LearningProjection(
        evidence, tuple(reviews[key] for key in sorted(reviews)), tuple(retention), policy,
        tuple(item.id for item in canonical if (item.task_id, item.task_revision) in excluded),
        tuple(sorted({item.task_id for item in canonical})),
        tuple(sorted({item.instance_id or item.task_id for item in canonical})),
    )


def slot_progress(
    projection: LearningProjection, slot_id: str, mandatory_skill_ids: Iterable[str],
) -> SlotProgress:
    policy = projection.policy
    attempts = [item for item in projection.evidence
                if item.slot_id == slot_id and item.independent]
    required = set(mandatory_skill_ids)
    covered = {skill for item in attempts if item.correct for skill in item.skill_ids} & required
    families = {item.family_id for item in attempts}
    days = {item.at.date() for item in attempts}
    retention = [item for item in projection.retention if item.slot_id == slot_id]
    retained = bool(retention) and retention[-1].success
    status = "Нет данных"
    if attempts:
        status = (
            "Закрепляю" if sum(item.correct for item in attempts[-policy.consolidating_window:])
            >= policy.consolidating_correct else "Изучаю"
        )
        if (
            len(attempts) >= policy.mastery_attempts
            and sum(item.correct for item in attempts[-policy.recent_window:])
            >= policy.recent_correct
            and len(families) >= policy.mastery_families and len(days) >= policy.mastery_days
            and covered == required and retained
        ):
            status = "Освоено"
    return SlotProgress(
        slot_id, status, len(attempts), sum(item.correct for item in attempts),
        len(covered), len(required), len(families), len(days),
    )
