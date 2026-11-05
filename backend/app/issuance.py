"""Bounded runtime fallback inside the caller's owner/catalog-locked transaction.

Selection is deterministic, not durable idempotency: core must replay a frozen
response before calling this module. Only the explicit server registry executes.
"""

import hashlib
import json
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import generators
from app.content import ContentBundle, ContentError, Task
from app.editor.models import (
    CorrectionExclusion,
    EditorPublication,
    EditorRevision,
    TemplateCheckRun,
    TemplateHumanReview,
)
from app.editor.schemas import TemplatePayload
from app.editor.validation import data_only, digest
from app.errors import ApiError
from app.generators.base import Family
from app.instances import Snapshot, instance_key, recent_exposure
from app.models import Guest
from app.schemas import CreateSessionRequest, ProfileSource

if TYPE_CHECKING:
    from app.services import LearningService

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 256
MAX_PER_TEMPLATE = 64
# The current explicit registry enforces both of these versions. Fail closed on upgrades.
GENERATOR_VERSION = "1"
TASK_REVISION = "1"
_MANIFEST_SEEDS = {str(seed) for seed in (*range(998), 2**32 - 2, 2**32 - 1)}
_CHECKS = {
    "strict_schema", "finite_exam_answer", "deterministic_snapshot",
    "profile_binding", "version_seed",
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class _Source:
    family: Family
    revision: EditorRevision | None = None


def deterministic_seed(owner_id: str, key: str, template_id: str, ordinal: int) -> int:
    """SHA-256's first 32 bits; callers supply the core-normalized request key."""
    if type(ordinal) is not int or ordinal < 0:
        raise ValueError("The seed ordinal must be a nonnegative integer")
    if any(not isinstance(value, str) for value in (owner_id, key, template_id)):
        raise TypeError("Seed namespace components must be strings")
    payload = json.dumps(
        ["runtime-v1", owner_id, key, template_id, ordinal],
        separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:4], "big")


def _checked_task(raw: Snapshot, family: Family, seed: int, profile: ProfileSource) -> Task:
    values = raw.model_dump(mode="python", warnings=False) if isinstance(raw, Task) else raw
    data_only(values)
    task = Task.model_validate(values)
    slot = next((slot for slot in profile.slots if slot.number == family.slot), None)
    if (
        slot is None or not set(family.skill_ids) <= {skill.id for skill in slot.skills}
        or task.id != f"course-{family.id}-{seed}" or task.revision != TASK_REVISION
        or task.family_id != family.id or task.slot != family.slot or task.slot_id != slot.id
        or task.profile_id != profile.id or set(task.skill_ids) != set(family.skill_ids)
        or task.generation is None or task.generation.seed != seed
        or task.generation.template_id != family.id
        or task.generation.template_version != GENERATOR_VERSION
        or task.review_status != "demo" or task.source.reviewed_by is not None
        or not all(value.strip() for value in (
            task.title, task.statement, task.topic,
            task.source.author, task.source.origin, task.source.rights,
        ))
    ):
        raise ContentError("Generated snapshot does not match its registered provenance")
    return task


def _reviewed_source(
    db: Session, pointer: EditorPublication, record: EditorRevision | None,
    runtime: Mapping[str, Family], profile: ProfileSource, now: datetime,
) -> _Source:
    if (
        record is None or pointer.withdrawn or pointer.kind != "template"
        or record.kind != "template" or record.status != "published"
        or record.content_id != pointer.content_id or record.id != pointer.revision_id
        or not record.author_id.strip() or not record.reviewer_id
        or not record.reviewer_id.strip() or record.author_id.strip() == record.reviewer_id.strip()
        or not record.reviewed_formula or not record.reviewed_constraints
        or record.reviewed_at is None or record.published_at is None
        or not record.created_at <= record.reviewed_at <= record.published_at <= now
        or not record.review_note or not record.review_note.strip()
    ):
        raise ContentError("Template publication lacks independent review")
    data_only(record.payload)
    payload = TemplatePayload.model_validate(record.payload)
    family = runtime.get(payload.generator_id)
    slot = next((slot for slot in profile.slots if slot.id == payload.slot_id), None)
    if (
        family is None or payload.id != record.content_id
        or record.payload_hash != digest(record.payload)
        or payload.generator_version != GENERATOR_VERSION or payload.profile_id != profile.id
        or payload.family_id != family.id or slot is None or slot.number != family.slot
        or set(payload.skill_ids) != set(family.skill_ids)
        or len(payload.skill_ids) != len(set(payload.skill_ids))
    ):
        raise ContentError("Template publication binding is invalid")
    profile_hash = digest(profile.model_dump(mode="json"))
    if payload.profile_revision_id is not None:
        linked = db.get(EditorRevision, payload.profile_revision_id)
        if (
            linked is None or linked.kind != "profile" or linked.status != "published"
            or linked.content_id != profile.id or digest(linked.payload) != profile_hash
        ):
            raise ContentError("Template profile evidence is stale")
    run = db.scalar(select(TemplateCheckRun).where(
        TemplateCheckRun.revision_id == record.id,
        TemplateCheckRun.payload_hash == record.payload_hash,
        TemplateCheckRun.profile_hash == profile_hash,
    ).order_by(
        TemplateCheckRun.checked_revision.desc(), TemplateCheckRun.created_at.desc(),
        TemplateCheckRun.id.desc(),
    ).limit(1))
    if (
        run is None or not run.passed or run.failure is not None or run.seed_count != 1000
        or run.generator_version != GENERATOR_VERSION
        or not 1 <= run.checked_revision <= record.revision
        or not record.created_at <= run.created_at <= record.reviewed_at
        or not isinstance(run.output_hashes, dict) or not isinstance(run.checks, list)
        or set(run.output_hashes) != _MANIFEST_SEEDS or not set(run.checks) >= _CHECKS
        or any(not isinstance(value, str) or not _HASH.fullmatch(value)
               for value in run.output_hashes.values())
    ):
        raise ContentError("Template automated evidence is missing or stale")
    scope = (
        TemplateHumanReview.revision_id == record.id,
        TemplateHumanReview.payload_hash == record.payload_hash,
        TemplateHumanReview.profile_hash == profile_hash,
    )
    rejected = db.scalar(select(TemplateHumanReview.id).where(
        *scope, TemplateHumanReview.approved.is_(False),
    ).limit(1))
    reviews = list(db.scalars(select(TemplateHumanReview).where(
        *scope, TemplateHumanReview.reviewer_id == record.reviewer_id,
        TemplateHumanReview.approved.is_(True),
    ).order_by(TemplateHumanReview.seed).limit(10)))
    if rejected is not None or len({review.seed for review in reviews}) != 10:
        raise ContentError("Template independent sample evidence is missing or rejected")
    for review in reviews:
        _checked_task(review.output_snapshot, family, review.seed, profile)
        if (
            digest(review.output_snapshot) != review.output_hash
            or not record.created_at <= review.created_at <= record.reviewed_at
            or not review.note.strip()
            or (str(review.seed) in run.output_hashes
                and review.output_hash != run.output_hashes[str(review.seed)])
        ):
            raise ContentError("Template sample evidence is stale")
    return _Source(family, record)


def _sources(
    db: Session, bundle: ContentBundle, allow_demo: bool, now: datetime,
    reject: Callable[[], None],
) -> list[_Source]:
    runtime = {family.id: family for family in generators.RUNTIME_FAMILIES}
    controlled, blocked = set(), set()
    sources: dict[str, _Source] = {}
    pointers = db.execute(select(EditorPublication, EditorRevision).outerjoin(
        EditorRevision, EditorRevision.id == EditorPublication.revision_id,
    ).where(EditorPublication.kind == "template").order_by(EditorPublication.content_id))
    for pointer, record in pointers:
        targets = {pointer.content_id} & runtime.keys()
        # A custom template ID can have a withdrawn NULL pointer. Its immutable
        # revisions still identify the generator it governed, including old bindings.
        revisions = list(db.scalars(select(EditorRevision).where(
            EditorRevision.kind == "template", EditorRevision.content_id == pointer.content_id,
        )))
        for revision in revisions:
            if isinstance(revision.payload, dict):
                identifier = revision.payload.get("generator_id")
                if isinstance(identifier, str) and identifier in runtime:
                    targets.add(identifier)
        if not targets:
            # Unknown provenance cannot establish that a withdrawal is harmless.
            reject()
            return []
        controlled.update(targets)
        if pointer.withdrawn:
            blocked.update(targets)
            continue
        try:
            source = _reviewed_source(db, pointer, record, runtime, bundle.profile, now)
        except (ValueError, TypeError, KeyError, ApiError):
            reject()
            blocked.update(targets)
        else:
            sources.setdefault(source.family.id, source)
    if allow_demo:
        for task in bundle.tasks:
            generation = task.generation
            if generation is None or generation.template_id not in runtime:
                continue
            identifier = generation.template_id
            if identifier in controlled or identifier in sources:
                continue
            if generation.template_version != GENERATOR_VERSION or task.review_status != "demo":
                continue
            family = runtime[identifier]
            try:
                _checked_task(task, family, generation.seed, bundle.profile)
            except (ValueError, TypeError, KeyError, ApiError):
                reject()
                continue
            sources[identifier] = _Source(family)
    return [source for identifier, source in sorted(sources.items()) if identifier not in blocked]


def _editor_blocks(db: Session) -> tuple[set[str], set[str]]:
    identifiers = set(db.scalars(select(EditorPublication.content_id).where(
        EditorPublication.kind == "task",
    )))
    identifiers.update(db.scalars(select(CorrectionExclusion.task_id)))
    keys = set()
    if identifiers:
        for record in db.scalars(select(EditorRevision).where(
            EditorRevision.kind == "task", EditorRevision.content_id.in_(identifiers),
        )):
            for snapshot in (record.payload, record.base_snapshot):
                if snapshot is not None:
                    keys.add(instance_key(snapshot))
    return identifiers, keys


def _reviewed_task(task: Task, record: EditorRevision) -> Task:
    raw = task.model_dump(mode="python")
    raw["review_status"] = "reviewed"
    raw["source"] = {
        **raw["source"], "author": record.author_id, "reviewed_by": record.reviewer_id,
        "origin": (
            f"Экземпляр опубликованного шаблона {record.content_id}, редакция {record.id}. "
            "Рецензия относится к шаблону, не к отдельному seed. "
            f"Исходное происхождение генератора: {task.source.origin}"
        ),
    }
    data_only(raw)
    return Task.model_validate(raw)


def historical_repeat_candidate(
    learning: "LearningService", db: Session, snapshot: Snapshot, bundle: ContentBundle, *,
    now: datetime | None = None,
) -> Task | None:
    """Reconstruct one explicit repeat after the caller verifies snapshot ownership.

    The caller holds canonical owner/catalog locks. This read-only helper grants
    no independent credit, writes no exposure history, and never trusts historical
    review attribution as publication authority. Current static IDs stay with core.
    """
    now = learning.clock() if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        return None
    try:
        values = (
            snapshot.model_dump(mode="python", warnings=False)
            if isinstance(snapshot, Task) else snapshot
        )
        data_only(values)
        historical = Task.model_validate(values)
        if any(task.id == historical.id for task in bundle.tasks):
            return None
        generation = historical.generation
        if generation is None:
            return None
        family = next((family for family in generators.RUNTIME_FAMILIES
                       if family.id == generation.template_id), None)
        if family is None:
            return None
        raw_profile = bundle.profile.model_dump(mode="python", warnings=False)
        data_only(raw_profile)
        profile = ProfileSource.model_validate(raw_profile)

        # Reuse the registered binding validator without treating old review
        # fields as authority. Only _sources below can authorize reconstruction.
        binding = historical.model_dump(mode="python")
        binding["review_status"] = "demo"
        binding["source"]["reviewed_by"] = None
        _checked_task(binding, family, generation.seed, profile)
        with db.no_autoflush:
            sources = _sources(
                db, ContentBundle(profile, bundle.lessons, bundle.tasks),
                learning.settings.allow_demo_content, now, lambda: None,
            )
            source = next((source for source in sources if source.family.id == family.id), None)
            if source is None:
                return None
            blocked_ids, blocked_keys = _editor_blocks(db)
        blocked_keys.update(
            instance_key(task) for task in bundle.tasks if task.id in blocked_ids
        )
        if historical.id in blocked_ids or instance_key(historical) in blocked_keys:
            return None
    except (ValueError, TypeError, KeyError, ApiError):
        # A policy/binding/exclusion denial is not an attempted generator outcome.
        return None

    try:
        raw = generators.generate(family.id, generation.seed, profile.model_copy(deep=True))
        task = _checked_task(raw, family, generation.seed, profile)
        attribution = {"source", "review_status"}
        if task.model_dump(exclude=attribution) != historical.model_dump(exclude=attribution):
            raise ContentError("Historical generator snapshot is not exactly reproducible")
        if source.revision is not None:
            task = _reviewed_task(task, source.revision)
    except Exception:
        learning.operation_health.record_event("generator", success=False)
        logger.warning("Historical repeat reconstruction failed.")
        return None
    learning.operation_health.record_event("generator", success=True)
    return task


def _bound(value: int, maximum: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 0 and {maximum}")


def generate_candidates(
    learning: "LearningService", db: Session, guest: Guest, request: CreateSessionRequest,
    key: str | None, bundle: ContentBundle, *, exclude: Iterable[str] = frozenset(),
    exclude_tasks: Iterable[Snapshot] = (), limit: int | None = None,
    slot_limits: Mapping[int, int] | None = None, now: datetime | None = None,
    max_attempts: int = MAX_ATTEMPTS, max_per_template: int = MAX_PER_TEMPLATE,
) -> tuple[list[Task], str | None]:
    """Return new, detached tasks and an explicit shortage, after static selection."""
    limit = request.length if limit is None else limit
    _bound(limit, 20, "limit")
    _bound(max_attempts, MAX_ATTEMPTS, "max_attempts")
    _bound(max_per_template, MAX_PER_TEMPLATE, "max_per_template")
    now = learning.clock() if now is None else now
    if now.tzinfo is None:
        raise ValueError("Issuance requires timezone-aware time")
    raw_profile = bundle.profile.model_dump(mode="python", warnings=False)
    data_only(raw_profile)
    profile = ProfileSource.model_validate(raw_profile)
    bundle = ContentBundle(profile, bundle.lessons, bundle.tasks)
    slots = {slot.number: slot for slot in profile.slots}
    if not set(request.slots) <= slots.keys():
        raise ApiError(422, "invalid_slots", "Позиция отсутствует в текущем профиле.")
    skills = {skill.id for number in request.slots for skill in slots[number].skills}
    families = {family.id for family in generators.RUNTIME_FAMILIES if family.slot in request.slots}
    families.update(task.family_id for task in bundle.tasks if task.slot in request.slots)
    if not set(request.skill_ids) <= skills or not set(request.family_ids) <= families:
        raise ApiError(
            422, "invalid_filters", "Подтема или семейство не входят в выбранные позиции.",
        )
    caps = dict.fromkeys(request.slots, limit) if slot_limits is None else dict(slot_limits)
    if not caps.keys() <= set(request.slots):
        raise ValueError("Slot limits must refer to requested slots")
    for value in caps.values():
        _bound(value, 20, "slot limit")
    if limit == 0:
        return [], None
    rejected = 0

    def reject() -> None:
        nonlocal rejected
        rejected += 1
        learning.operation_health.record_event("generator", success=False)

    sources = _sources(db, bundle, learning.settings.allow_demo_content, now, reject)
    sources = [source for source in sources if source.family.slot in request.slots
               and (not request.family_ids or source.family.id in request.family_ids)
               and (not request.skill_ids or set(source.family.skill_ids) & set(request.skill_ids))]
    sources.sort(key=lambda source: (request.slots.index(source.family.slot), source.family.id))
    owners = learning.owner_ids(db, guest)
    try:
        blocked_ids, blocked_keys = _editor_blocks(db)
        # All existing bank IDs belong to static selection. Re-generating one would
        # risk bypassing an editorial override or an earlier static eligibility gate.
        blocked_ids.update(task.id for task in bundle.tasks)
        exposure = recent_exposure(
            db, owners, bundle.tasks, now,
            exclude=set(exclude) | blocked_ids, exclude_tasks=exclude_tasks,
        )
    except (ValueError, TypeError, KeyError):
        # Incomplete exclusion knowledge cannot authorize any new instance.
        # Infrastructure/authorization errors still propagate to the caller.
        reject()
        sources = []
        used_ids, used_keys = set(), set()
    else:
        used_ids, used_keys = set(exposure.ids), set(exposure.keys) | blocked_keys
    selected: list[Task] = []
    counts: Counter[int] = Counter()
    attempts = 0
    for ordinal in range(max_per_template):
        for source in sources:
            if len(selected) >= limit or attempts >= max_attempts or request.repeat_task_id:
                break
            family = source.family
            if counts[family.slot] >= caps.get(family.slot, 0):
                continue
            seed = deterministic_seed(guest.id, key or "", family.id, ordinal)
            attempts += 1
            try:
                raw = generators.generate(family.id, seed, profile.model_copy(deep=True))
                task = _checked_task(raw, family, seed, profile)
                if source.revision is not None:
                    task = _reviewed_task(task, source.revision)
                signature = instance_key(task)
            except Exception:
                # Registered code may fail in an oracle/domain check. Exception
                # strings, tracebacks and task values must not enter logs or notices.
                reject()
                continue
            learning.operation_health.record_event("generator", success=True)
            if (
                task.id in used_ids or signature in used_keys
                or (request.difficulty is not None and task.difficulty != request.difficulty)
            ):
                continue
            selected.append(task)
            used_ids.add(task.id)
            used_keys.add(signature)
            counts[task.slot] += 1
        if len(selected) >= limit or attempts >= max_attempts or not sources:
            break
    if rejected:
        logger.warning("Runtime issuance rejected %d source/output checks.", rejected)
    notice = None if len(selected) == limit else (
        f"Дополнительно доступно {len(selected)} из {limit} новых задач. "
        "Подбор ограничен; знакомые, исключённые и недоступные экземпляры не повторяются."
    )
    return selected, notice
