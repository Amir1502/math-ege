"""Structural condition identity over immutable, original-owner task snapshots.

Call database helpers under the caller's canonical owner lock. They may fill a
legacy NULL exposure key, but never commit or rewrite a historical snapshot.
"""

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, NamedTuple
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assessments.models import AssessmentRecord
from app.content import ContentError, Task
from app.models import LearningSessionRecord, SeenTask
from app.schemas import Figure, Rounding, Schema, TaskTable

type Snapshot = Task | dict[str, Any]
_KEY = re.compile(r"[0-9a-f]{64}\Z")


class _Condition(Schema):
    statement: str
    formula: str | None = None
    table: TaskTable | None = None
    figure: Figure | None = None
    rounding: Rounding | None = None


def _values(snapshot: Snapshot) -> dict[str, Any]:
    if isinstance(snapshot, Task):
        return snapshot.model_dump(mode="python", warnings=False)
    if not isinstance(snapshot, dict):
        raise TypeError("A task snapshot must be a Task or a dictionary")
    return snapshot


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, float) and value.is_integer():
        return int(value)  # Includes negative zero; no numeric guessing inside text.
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def instance_key(snapshot: Snapshot) -> str:
    """SHA-256 of visible structure only; metadata and solutions are not identity."""
    raw = _values(snapshot)
    condition = {name: raw[name] for name in _Condition.model_fields if name in raw}
    # Identity is independent of today's rendering/TeX allowlist. Historical
    # text is hashed, never rendered or executed; issuance validates new output.
    parsed = _Condition.model_validate(_normalize(condition))
    if not parsed.statement.strip():
        raise ContentError("A task condition cannot be empty")
    canonical = _normalize(parsed.model_dump(mode="python"))
    return hashlib.sha256(json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


class Exposure(NamedTuple):
    ids: frozenset[str]
    keys: frozenset[str]


class TaskAliases(NamedTuple):
    ids: frozenset[str]
    records: tuple[SeenTask, ...]


@dataclass(slots=True)
class _History:
    records: tuple[SeenTask, ...]
    by_origin: dict[tuple[str, str], set[str]]
    by_id: dict[str, set[str]]
    occurrences: list[tuple[datetime, str, str]]


def _provided(tasks: Iterable[Snapshot]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for task in tasks:
        raw = _values(task)
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ContentError("A historical task requires its original ID")
        result[identifier].add(instance_key(task))
    return result


def _history(db: Session, owners: Iterable[str], tasks: Iterable[Snapshot]) -> _History:
    if isinstance(owners, str):
        raise TypeError("Pass server-resolved owner IDs, not a single string")
    scope = tuple(sorted(set(owners)))
    by_origin: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_id: dict[str, set[str]] = defaultdict(set)
    occurrences = []
    if not scope:
        return _History((), by_origin, by_id, occurrences)
    first: dict[tuple[str, str], tuple] = {}
    for model in (LearningSessionRecord, AssessmentRecord):
        rows = db.execute(select(
            model.guest_id, model.id, model.created_at, model.tasks_snapshot,
        ).where(model.guest_id.in_(scope)).execution_options(yield_per=100))
        for owner, record_id, at, snapshots in rows:
            if not isinstance(snapshots, list):
                raise ContentError("Historical tasks must be a list of snapshots")
            for index, task in enumerate(snapshots):
                task = _values(task)
                identifier = task.get("id")
                if not isinstance(identifier, str) or not identifier:
                    raise ContentError("A historical task requires its original ID")
                key = instance_key(task)
                origin = (owner, identifier)
                by_origin[origin].add(key)
                by_id[identifier].add(key)
                occurrences.append((at, identifier, key))
                order = (at, model.__tablename__, record_id, index, key)
                if origin not in first or order < first[origin]:
                    first[origin] = order
    fallback = _provided(tasks)
    records = tuple(db.scalars(select(SeenTask).where(
        SeenTask.guest_id.in_(scope),
    ).order_by(SeenTask.guest_id, SeenTask.task_id, SeenTask.id)))
    for record in records:
        origin = (record.guest_id, record.task_id)
        if record.instance_key is None:
            if origin in first:
                record.instance_key = first[origin][-1]
            elif len(fallback.get(record.task_id, ())) == 1:
                record.instance_key = next(iter(fallback[record.task_id]))
        if record.instance_key is not None:
            if not _KEY.fullmatch(record.instance_key):
                raise ContentError("Invalid stored instance key")
            by_origin[origin].add(record.instance_key)
            by_id[record.task_id].add(record.instance_key)
        elif origin not in first:
            # Ambiguous fallback conditions can exclude aliases without inventing a key.
            by_origin[origin].update(fallback.get(record.task_id, ()))
            by_id[record.task_id].update(fallback.get(record.task_id, ()))
    return _History(records, by_origin, by_id, occurrences)


def recent_exposure(
    db: Session, owners: Iterable[str], tasks: Iterable[Snapshot], now: datetime, *,
    days: int = 30, exclude: Iterable[str] = (), exclude_tasks: Iterable[Snapshot] = (),
) -> Exposure:
    """Recent IDs/keys plus age-independent exclusions, including all prior batches."""
    if now.tzinfo is None or type(days) is not int or days < 0:
        raise ValueError("Exposure requires aware time and a nonnegative day window")
    tasks = tuple(tasks)
    history = _history(db, owners, tasks)
    cutoff = now - timedelta(days=days)
    ids, keys = set(), set()
    for at, identifier, key in history.occurrences:
        if at > cutoff:
            ids.add(identifier)
            keys.add(key)
    for record in history.records:
        if record.last_seen_at > cutoff:
            ids.add(record.task_id)
            keys.update(history.by_origin[(record.guest_id, record.task_id)])
    provided = _provided(tasks)
    explicit = _provided(exclude_tasks)
    excluded_ids = set(exclude) | explicit.keys()
    ids.update(excluded_ids)
    for identifier in excluded_ids:
        keys.update(history.by_id.get(identifier, ()))
        keys.update(provided.get(identifier, ()))
        keys.update(explicit.get(identifier, ()))
    return Exposure(frozenset(ids), frozenset(keys))


def aliases_for_task(
    db: Session, owners: Iterable[str], snapshot: Snapshot, *, tasks: Iterable[Snapshot] = (),
) -> TaskAliases:
    """Actual original IDs and SeenTask rows for help/attempt/assessment joins."""
    key = instance_key(snapshot)
    identifier = _values(snapshot)["id"]
    history = _history(db, owners, (*tasks, snapshot))
    ids = {identifier, *(task_id for task_id, keys in history.by_id.items() if key in keys)}
    # Same-ID legacy facts stay conservative even if a correction changed its condition.
    return TaskAliases(frozenset(ids), tuple(
        record for record in history.records if record.task_id in ids
    ))


def mark_instances(
    db: Session, owner_id: str, tasks: Iterable[Snapshot], now: datetime,
) -> tuple[SeenTask, ...]:
    """Mark issuance in the session's ORIGINAL owner scope, retaining historical facts."""
    if now.tzinfo is None:
        raise ValueError("Exposure timestamps must be timezone-aware")
    tasks = tuple(tasks)
    provided = _provided(tasks)
    if any(len(keys) != 1 for keys in provided.values()):
        raise ContentError("One issuance cannot contain conflicting snapshots of a task ID")
    records = {record.task_id: record for record in db.scalars(select(SeenTask).where(
        SeenTask.guest_id == owner_id, SeenTask.task_id.in_(provided),
    ))}
    if any(record.instance_key is None for record in records.values()):
        _history(db, [owner_id], tasks)
    for identifier, keys in provided.items():
        if identifier in records:
            record = records[identifier]
            record.last_seen_at = max(record.last_seen_at, now)
        else:
            record = SeenTask(
                id=str(uuid4()), guest_id=owner_id, task_id=identifier,
                instance_key=next(iter(keys)), first_seen_at=now, last_seen_at=now,
                assistance_seen=False, reference_seen=False,
            )
            db.add(record)
            records[identifier] = record
    return tuple(records[identifier] for identifier in provided)
