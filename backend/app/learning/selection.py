"""Deterministic, disjoint mixed practice selection; issuance stays in the core."""

import hashlib
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Protocol

from sqlalchemy.orm import Session

from app.content import ContentBundle, Task
from app.instances import instance_key, recent_exposure
from app.learning.policy import DEFAULT_POLICY, LearningPolicy, LearningProjection
from app.models import Guest


class SelectionRequest(Protocol):
    slots: list[int]
    length: int
    skill_ids: list[str]
    family_ids: list[str]
    difficulty: int | None
    repeat_task_id: str | None


@dataclass(frozen=True, slots=True)
class Selection:
    tasks: tuple[Task, ...]
    quotas: tuple[int, int, int]
    counts: tuple[int, int, int]
    notice: str | None


def quotas(length: int, policy: LearningPolicy = DEFAULT_POLICY) -> tuple[int, int, int]:
    """Largest remainders; equal remainders favor weak, then review, then new."""
    weights = policy.selection_weights
    total = sum(weights)
    result = [length * weight // total for weight in weights]
    order = sorted(range(3), key=lambda index: (-(length * weights[index] % total), index))
    for index in order[:length - sum(result)]:
        result[index] += 1
    return tuple(result)


def _family_rounds(tasks: list[Task]) -> list[Task]:
    families: dict[str, deque[Task]] = defaultdict(deque)
    for task in tasks:
        families[task.family_id].append(task)
    result = []
    while families:
        for family in list(families):
            result.append(families[family].popleft())
            if not families[family]:
                del families[family]
    return result


def mixed_candidates(
    bundle: ContentBundle, request: SelectionRequest, projection: LearningProjection,
    seen_at: Mapping[str, datetime], now: datetime, salt: str, *, owner_id: str = "",
    instance_aware: bool = False,
) -> Selection:
    """Pure selection seam. The bundle must already contain only permitted tasks.

    Due fresh instances take precedence over other groups, then unseen families,
    then familiar families ranked by skill weakness. Thus quotas cannot compete
    for the same candidate. Shortages use remaining weak candidates, then new.
    Instance-aware callers supply exposure timestamps by key or legacy task ID;
    aliases share one candidate and one encountered identity. Keyed projections
    enable this automatically; the flag also enables it for empty/legacy history.
    Unkeyed pure calls retain the legacy task-ID contract.
    """
    policy = projection.policy
    targets = quotas(request.length, policy)
    cutoff = now - timedelta(days=policy.instance_exclusion_days)
    exposed_tasks = set(projection.encountered_task_ids)
    exposed_instances = set(projection.encountered_instance_ids)
    instance_aware = instance_aware or bool(exposed_instances - exposed_tasks) or any(
        item.instance_id is not None for item in projection.evidence
    )
    candidates = [task for task in bundle.tasks if (
        task.slot in request.slots
        and (not request.skill_ids or set(task.skill_ids) & set(request.skill_ids))
        and (not request.family_ids or task.family_id in request.family_ids)
        and (request.difficulty is None or task.difficulty == request.difficulty)
    )]
    if request.repeat_task_id is not None:
        repeated = tuple(task for task in candidates if task.id == request.repeat_task_id)
        return Selection(
            repeated, targets, (len(repeated), 0, 0), "Выбран явный повтор экземпляра.",
        )
    identities = {task.id: instance_key(task) if instance_aware else task.id
                  for task in candidates}
    candidates = [task for task in candidates if all(
        identity not in seen_at or seen_at[identity] <= cutoff
        for identity in (task.id, identities[task.id])
    )]
    independent = [item for item in projection.evidence if item.independent]
    known_families = {item.family_id for item in independent}
    exposed = (exposed_instances or exposed_tasks) if instance_aware else exposed_tasks
    due = {(item.skill_id, item.family_id): item for item in projection.reviews
           if item.due_at is not None and item.due_at <= now}
    priorities = {}
    for slot in bundle.profile.slots:
        for skill in slot.skills:
            attempts = [item for item in independent if skill.id in item.skill_ids]
            recent = attempts[-policy.recent_window:]
            priorities[skill.id] = (
                any(item.correct for item in attempts),
                Fraction(sum(item.correct for item in recent), len(recent) or 1),
                attempts[-1].at if attempts else datetime.min.replace(tzinfo=UTC),
            )

    def shuffled(task: Task) -> bytes:
        return hashlib.sha256(f"{owner_id}\0{salt}\0{task.id}".encode()).digest()

    def weakness(task: Task) -> tuple:
        return min(priorities.get(skill, (False, Fraction(0), datetime.min.replace(tzinfo=UTC)))
                   for skill in task.skill_ids)

    groups: list[list[Task]] = [[], [], []]
    deadlines = {}
    for task in candidates:
        relevant = [due[(skill, task.family_id)] for skill in task.skill_ids
                    if (skill, task.family_id) in due]
        if relevant and identities[task.id] not in exposed and task.id not in exposed:
            groups[1].append(task)
            deadlines[task.id] = min(item.due_at for item in relevant)
        elif task.family_id not in known_families:
            groups[2].append(task)
        else:
            groups[0].append(task)
    groups[0].sort(key=lambda task: (weakness(task), shuffled(task), task.id))
    groups[1].sort(key=lambda task: (deadlines[task.id], shuffled(task), task.id))
    groups[2].sort(key=lambda task: (shuffled(task), task.id))
    groups[2] = _family_rounds(groups[2])
    assigned: set[str] = set()
    for index in (1, 2, 0):
        distinct = []
        for task in groups[index]:
            identity = identities[task.id]
            if identity not in assigned:
                distinct.append(task)
                assigned.add(identity)
        groups[index] = distinct
    chosen = [group[:target] for group, target in zip(groups, targets, strict=True)]
    missing = request.length - sum(map(len, chosen))
    for index in (0, 2):
        extra = groups[index][len(chosen[index]):len(chosen[index]) + missing]
        chosen[index].extend(extra)
        missing -= len(extra)
    counts = tuple(map(len, chosen))
    tasks = tuple(task for group in chosen for task in group)
    notice = None
    if len(tasks) < request.length:
        notice = (
            f"Доступно {len(tasks)} из {request.length} задач для выбранного состава серии. "
            "Уже выданные за 30 дней экземпляры исключены; скрытых повторов нет."
        )
    elif counts != targets:
        notice = (
            f"Доли перераспределены из-за нехватки кандидатов: слабые навыки — {counts[0]}, "
            f"повторение — {counts[1]}, новые семейства — {counts[2]}."
        )
    return Selection(tasks, targets, counts, notice)


def selection_details(
    db: Session, guest: Guest, bundle: ContentBundle, request: SelectionRequest,
    now: datetime, salt: str, *, policy: LearningPolicy = DEFAULT_POLICY,
) -> Selection:
    """Reuse the caller's canonical owner write lock; exposure may fill legacy NULL keys."""
    from app.accounts.principals import owner_ids, root_owner_id
    from app.learning.evidence import editorial_exclusions, load_history
    from app.learning.policy import replay

    owners = owner_ids(db, guest)
    history = load_history(db, owners)
    excluded = editorial_exclusions(db)
    projection = replay(history.events, policy, exclusions=excluded)
    exposure = recent_exposure(
        db, owners, bundle.tasks, now, days=policy.instance_exclusion_days,
    )
    permitted = ContentBundle(bundle.profile, bundle.lessons, tuple(
        task for task in bundle.tasks if (task.id, task.revision) not in excluded
        and (request.repeat_task_id is not None or (
            task.id not in exposure.ids and instance_key(task) not in exposure.keys
        ))
    ))
    return mixed_candidates(permitted, request, projection, {}, now, salt,
                            owner_id=root_owner_id(db, guest.id), instance_aware=True)


def seen_instances(db: Session, owners: list[str]) -> dict[str, datetime]:
    from sqlalchemy import select

    from app.models import SeenTask

    seen_at = {}
    for record in db.scalars(select(SeenTask).where(SeenTask.guest_id.in_(owners))):
        previous = seen_at.get(record.task_id, record.last_seen_at)
        seen_at[record.task_id] = max(record.last_seen_at, previous)
    return seen_at


def select_tasks(
    db: Session, guest: Guest, bundle: ContentBundle, request: SelectionRequest,
    now: datetime, salt: str,
) -> list[Task]:
    return list(selection_details(db, guest, bundle, request, now, salt).tasks)
