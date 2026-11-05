"""The published overlay and read-only correction adapters used by learning services."""

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.content import ContentBundle, ContentError, load_content, validate_content
from app.database import Database
from app.editor.models import (
    CorrectionExclusion,
    EditorCatalog,
    EditorPublication,
    EditorRevision,
)
from app.editor.validation import validate_links
from app.models import AttemptRecord


def lock_catalog(db: Session) -> EditorCatalog:
    """Migrations seed this row; lazy insertion also supports create_schema_for_tests."""
    catalog = db.scalar(select(EditorCatalog).where(EditorCatalog.id == 1).with_for_update())
    if catalog is None:
        try:
            with db.begin_nested():
                db.add(EditorCatalog(id=1, revision=0, profile_revision_id=None))
                db.flush()
        except IntegrityError:
            # Another PostgreSQL writer inserted the singleton while we waited.
            pass
        catalog = db.scalar(
            select(EditorCatalog)
            .where(EditorCatalog.id == 1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    if catalog is None:
        raise ContentError("Не удалось получить блокировку каталога.")
    return catalog


def base_payloads(settings: Settings) -> dict[str, dict[str, dict[str, Any]]]:
    bundle = load_content(settings.content_dir)
    return {
        "profile": {bundle.profile.id: bundle.profile.model_dump(mode="json")},
        "lesson": {lesson.id: lesson.model_dump(mode="json") for lesson in bundle.lessons},
        "task": {task.id: task.model_dump(mode="json") for task in bundle.tasks},
        "template": {},
    }


def combined_content(
    db: Session,
    settings: Settings,
    candidates: list[EditorRevision] | None = None,
) -> ContentBundle:
    """Validate a candidate package against one locked, coherent set of active pointers.

    Withdrawn practice links are pruned in this read projection only. Stored lesson
    payloads and all issued snapshots retain their original references. A newly
    submitted lesson must itself stop referring to a withdrawn task.
    """
    base = load_content(settings.content_dir)
    profile = base.profile.model_dump(mode="json")
    tasks = {task.id: task.model_dump(mode="json") for task in base.tasks}
    lessons = {lesson.id: lesson.model_dump(mode="json") for lesson in base.lessons}
    # PostgreSQL READ COMMITTED takes a new snapshot per statement. A shared
    # catalog lock keeps profile and pointer reads in the same publication epoch.
    # SQLite's explicit read transaction already supplies a consistent snapshot.
    catalog = db.scalar(
        select(EditorCatalog).where(EditorCatalog.id == 1).with_for_update(read=True)
    )
    if catalog is not None and catalog.profile_revision_id is not None:
        revision = db.get(EditorRevision, catalog.profile_revision_id)
        if revision is None or revision.status != "published":
            raise ContentError("Опубликованный профиль недоступен.")
        profile = copy.deepcopy(revision.payload)
    withdrawn: set[str] = set()
    withdrawn_families: set[str] = set()
    pointers = (
        db.execute(
            select(EditorPublication, EditorRevision).outerjoin(
                EditorRevision,
                EditorRevision.id == EditorPublication.revision_id,
            ),
        )
        if catalog is not None
        else []
    )
    for pointer, revision in pointers:
        target = tasks if pointer.kind == "task" else lessons if pointer.kind == "lesson" else None
        if target is None:
            continue
        if pointer.withdrawn:
            target.pop(pointer.content_id, None)
            if pointer.kind == "task":
                withdrawn.add(pointer.content_id)
                if revision is not None:
                    withdrawn_families.add(revision.payload["family_id"])
        elif revision is None or revision.status != "published":
            raise ContentError("Опубликованная редакция недоступна.")
        else:
            target[pointer.content_id] = copy.deepcopy(revision.payload)

    candidates = candidates or []
    if sum(candidate.kind == "profile" for candidate in candidates) > 1:
        raise ContentError("За одну публикацию можно выбрать только один профиль.")
    # Withdrawals must not make the rest of the bank unavailable. Only existing
    # links are projected away; new candidate lessons are validated unmodified.
    surviving_families = {task["family_id"] for task in tasks.values()}
    withdrawn_families.update(task.family_id for task in base.tasks if task.id in withdrawn)
    for lesson in lessons.values():
        lesson["practice_task_ids"] = [
            identifier
            for identifier in lesson.get("practice_task_ids", [])
            if identifier not in withdrawn
        ]
        lesson["family_ids"] = [
            identifier
            for identifier in lesson.get("family_ids", [])
            if identifier not in withdrawn_families or identifier in surviving_families
        ]
    for candidate in candidates:
        if candidate.kind == "profile":
            profile = copy.deepcopy(candidate.payload)
        elif candidate.kind == "task":
            tasks[candidate.content_id] = copy.deepcopy(candidate.payload)
        elif candidate.kind == "lesson":
            lessons[candidate.content_id] = copy.deepcopy(candidate.payload)

    # Legacy records without slot_id belong to their original stable slot, never
    # whichever skill happens to acquire the same numeric position later.
    original_slots = {slot.number: slot.id for slot in base.profile.slots}
    current_slots = {slot["number"]: slot["id"] for slot in profile["slots"]}
    for item in [*tasks.values(), *lessons.values()]:
        stable = item.get("slot_id") or original_slots.get(item["slot"])
        if stable != current_slots.get(item["slot"]):
            raise ContentError("Нужна явная привязка задач и уроков к стабильным slot_id.")
    bundle = validate_content(profile, list(lessons.values()), list(tasks.values()))
    validate_links(bundle)
    return bundle


def published_content(database: Database, settings: Settings) -> ContentBundle:
    """No drafts or archived/base fallback. Issuance still honors ALLOW_DEMO_CONTENT."""
    with database.transaction() as db:
        bundle = combined_content(db, settings)
        return ContentBundle(
            bundle.profile,
            bundle.lessons,
            bundle.available_tasks(allow_demo_content=settings.allow_demo_content),
        )


def exclusions(db: Session) -> dict[tuple[str, str], str]:
    """Projection input only: consumers exclude mastery evidence, never frozen scores."""
    return {
        (record.task_id, record.task_revision): record.reason
        for record in db.scalars(select(CorrectionExclusion))
    }


def notices(db: Session, guest_ids: list[str]) -> list[dict[str, Any]]:
    """Pass only server-resolved owner_ids. Assessment notices wait for answer release."""
    if not guest_ids:
        return []
    corrections = {
        (record.task_id, record.task_revision): record
        for record in db.scalars(select(CorrectionExclusion))
    }
    if not corrections:
        return []
    affected: dict[tuple[str, str], dict[str, Any]] = {}

    def entry(key: tuple[str, str]) -> dict[str, Any]:
        if key not in affected:
            record = corrections[key]
            affected[key] = {
                "id": record.id,
                "task_id": record.task_id,
                "task_revision": record.task_revision,
                "reason": record.reason,
                "created_at": record.created_at.isoformat(),
                "attempt_ids": [],
                "session_ids": [],
                "assessment_ids": [],
                "effect": "excluded_from_mastery",
                "historical_scores_unchanged": True,
            }
        return affected[key]

    attempts = db.scalars(select(AttemptRecord).where(AttemptRecord.guest_id.in_(guest_ids)))
    for attempt in attempts:
        key = (attempt.task_id, attempt.task_revision)
        if key in corrections:
            item = entry(key)
            item["attempt_ids"].append(attempt.id)
            if attempt.session_id not in item["session_ids"]:
                item["session_ids"].append(attempt.session_id)

    from app.assessments.models import AssessmentRecord

    assessments = db.scalars(
        select(AssessmentRecord).where(
            AssessmentRecord.guest_id.in_(guest_ids),
            AssessmentRecord.status == "completed",
            AssessmentRecord.released_at.is_not(None),
        )
    )
    for assessment in assessments:
        for task in assessment.tasks_snapshot:
            key = (task["id"], task["revision"])
            if key in corrections:
                entry(key)["assessment_ids"].append(assessment.id)
    for item in affected.values():
        for field in ("attempt_ids", "session_ids", "assessment_ids"):
            item[field] = sorted(set(item[field]))
    return sorted(affected.values(), key=lambda item: (item["created_at"], item["id"]))
