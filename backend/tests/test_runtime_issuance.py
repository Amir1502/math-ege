"""Direct helper contracts, not assertions that practice/assessment wiring exists."""

import copy
import hashlib
import json
import re
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from math import isqrt
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text

from app import generators
from app.accounts.models import Account, GuestClaim
from app.assessments.models import AssessmentRecord
from app.config import Settings
from app.content import ContentBundle, Task, load_content
from app.database import Database
from app.editor.models import (
    CorrectionExclusion,
    EditorPublication,
    EditorRevision,
    TemplateCheckRun,
    TemplateHumanReview,
)
from app.editor.repository import lock_catalog
from app.editor.validation import digest
from app.generators.base import make_task
from app.instances import aliases_for_task, instance_key, mark_instances, recent_exposure
from app.issuance import (
    deterministic_seed,
    generate_candidates,
    historical_repeat_candidate,
)
from app.models import Guest, LearningSessionRecord, SeenTask
from app.operations.health import OperationHealth
from app.schemas import CreateSessionRequest, Schema
from app.services import LearningService

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
KEY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
LEGACY = Path(__file__).resolve().parents[1] / "content"
FAMILY = "right-triangle-area"
MANIFEST_SEEDS = (*range(998), 2**32 - 2, 2**32 - 1)
CHECKS = [
    "strict_schema", "finite_exam_answer", "deterministic_snapshot",
    "profile_binding", "version_seed",
]


@pytest.fixture
def legacy_dir(tmp_path):
    """Explicit copies of the original package, independent of DEFAULT_CONTENT_DIR."""
    directory = tmp_path / "legacy-content"
    directory.mkdir()
    for name in ("profile.json", "lessons.json", "tasks.json"):
        (directory / name).write_bytes((LEGACY / name).read_bytes())
    return directory


@pytest.fixture
def world(tmp_path, legacy_dir):
    legacy = load_content(legacy_dir)
    assert len(legacy.tasks) == 65
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'issuance.sqlite3').as_posix()}",
        content_dir=legacy_dir, allow_demo_content=True,
    )
    database = Database(settings)
    database.create_schema_for_tests()
    learning = LearningService(database, settings, clock=lambda: NOW)
    learning.operation_health = OperationHealth(now=NOW)
    with database.transaction(write=True) as db:
        guest = _guest(db)
    anchor = generators.generate(FAMILY, 0, legacy.profile)
    result = SimpleNamespace(
        database=database, learning=learning, guest=guest, legacy=legacy,
        bundle=ContentBundle(legacy.profile, (), (anchor,)),
    )
    try:
        yield result
    finally:
        database.dispose()


def _guest(db):
    identifier = str(uuid4())
    guest = Guest(
        id=identifier, token_digest=hashlib.sha256(identifier.encode()).hexdigest(),
        created_at=NOW - timedelta(days=100), expires_at=NOW + timedelta(days=365),
        last_seen_at=NOW,
    )
    db.add(guest)
    db.flush()
    return guest


def _request(**values):
    return CreateSessionRequest.model_validate({
        "slots": [1], "length": 5, "mode": "practice", "family_ids": [FAMILY], **values,
    })


def _practice(db, owner, tasks, profile, at=NOW):
    record = LearningSessionRecord(
        id=str(uuid4()), guest_id=owner.id, profile_id=profile.id,
        profile_revision=profile.revision, profile_snapshot=profile.model_dump(mode="json"),
        tasks_snapshot=copy.deepcopy(tasks), mode="practice", status="active", created_at=at,
        completed_at=None, current_index=0, requested_length=5, notice=None, draft_revision=0,
        options_snapshot=None, drafts={}, help_state={}, active_seconds={}, summary_snapshot=None,
    )
    db.add(record)
    return record


def _assessment(db, owner, tasks, profile, at=NOW):
    record = AssessmentRecord(
        id=str(uuid4()), guest_id=owner.id, profile_id=profile.id,
        profile_revision=profile.revision, profile_snapshot=profile.model_dump(mode="json"),
        tasks_snapshot=copy.deepcopy(tasks), mode="diagnostic", status="prepared", created_at=at,
        started_at=None, deadline_at=None, released_at=None, duration_minutes=60,
        writer_device_id=str(uuid4()), writer_generation=1, draft_revision=0, current_index=0,
        drafts={}, first_drafts={}, answer_context={}, server_result=None, local_result=None,
        finish_hash=None,
    )
    db.add(record)
    return record


def _seen(db, owner, task_id, at=NOW, **values):
    row = SeenTask(
        id=str(uuid4()), guest_id=owner.id, task_id=task_id, instance_key=None,
        first_seen_at=at, last_seen_at=at, assistance_seen=False, reference_seen=False,
    )
    for name, value in values.items():
        setattr(row, name, value)
    db.add(row)
    return row


def _published(db, world, *, reviews=10, pointer=True):
    """Synthetic editorial evidence in a new test DB, never real human attestation."""
    task = world.bundle.tasks[0]
    payload = {
        "id": "synthetic-reviewed-template", "title": "Synthetic template fixture",
        "generator_id": FAMILY, "generator_version": "1", "profile_id": task.profile_id,
        "profile_revision_id": None, "slot_id": task.slot_id, "family_id": FAMILY,
        "skill_ids": task.skill_ids, "formula_notes": "Synthetic formula review fixture",
        "constraints": ["Synthetic domain review fixture"],
    }
    record = EditorRevision(
        id=str(uuid4()), kind="template", content_id=payload["id"], version=1, revision=4,
        status="published", title=payload["title"], payload=payload, payload_hash=digest(payload),
        base_snapshot=None, parent_id=None, author_id="synthetic-author",
        reviewer_id="synthetic-reviewer", change_note="Synthetic test data",
        review_note="Synthetic test data, not a real course review",
        reviewed_formula=True, reviewed_constraints=True,
        created_at=NOW - timedelta(minutes=5), updated_at=NOW - timedelta(minutes=1),
        reviewed_at=NOW - timedelta(minutes=2), published_at=NOW - timedelta(minutes=1),
    )
    db.add(record)
    db.flush()
    outputs = {
        seed: generators.generate(FAMILY, seed, world.bundle.profile).model_dump(mode="json")
        for seed in MANIFEST_SEEDS
    }
    run = TemplateCheckRun(
        id=str(uuid4()), revision_id=record.id, payload_hash=record.payload_hash,
        profile_hash=digest(world.bundle.profile.model_dump(mode="json")),
        generator_version="1", checked_revision=2, seed_count=1000,
        output_hashes={str(seed): digest(value) for seed, value in outputs.items()},
        checks=CHECKS, passed=True, failure=None, actor_id="synthetic-author",
        created_at=NOW - timedelta(minutes=3),
    )
    db.add(run)
    for seed in range(reviews):
        db.add(TemplateHumanReview(
            id=str(uuid4()), revision_id=record.id, payload_hash=record.payload_hash,
            profile_hash=run.profile_hash, seed=seed, output_hash=digest(outputs[seed]),
            output_snapshot=outputs[seed], approved=True, reviewer_id=record.reviewer_id,
            note="Synthetic test sample only", created_at=NOW - timedelta(minutes=3),
        ))
    publication = EditorPublication(
        kind="template", content_id=record.content_id, revision_id=record.id,
        withdrawn=False, reason=None, updated_at=NOW - timedelta(minutes=1),
    )
    if pointer:
        db.add(publication)
    db.flush()
    return record, publication, run


def _generate(world, db, request=None, **options):
    lock_catalog(db)
    return generate_candidates(
        world.learning, db, world.guest, request or _request(), KEY, world.bundle, **options,
    )


def _synthetic_bank(world, monkeypatch, families):
    """Exercise issuance independently of unrelated course/editor validation work."""
    by_id = {family.id: family for family in families}

    def generate(identifier, seed, profile):
        family = by_id[identifier]
        return Task.model_validate(make_task(
            profile, family.slot, family.id, seed, title="Synthetic addition",
            statement=f"Synthetic fixture: find {seed} + {family.slot}.",
            answer=seed + family.slot, skills=list(family.skill_ids),
            hints=["Add the numbers.", "Use exact integers.", "Keep the last digit."],
            solution=[f"The sum is {seed + family.slot}."],
        ))

    monkeypatch.setattr(generators, "generate", generate)
    world.bundle = ContentBundle(world.bundle.profile, (), tuple(
        generate(family.id, 0, world.bundle.profile) for family in families
    ))


@pytest.mark.parametrize("field,value", [
    ("id", "alias-id"), ("revision", "another-revision"), ("title", "Other title"),
    ("topic", "Other topic"), ("profile_id", "other-profile"), ("difficulty", 3),
    ("source", {"unrelated": "metadata"}), ("answer", "999"),
    ("generation", {"template_id": "alias", "template_version": "2", "seed": 42}),
])
def test_signature_excludes_noncondition_metadata(world, field, value):
    task = world.bundle.tasks[0]
    alias = task.model_dump(mode="json")
    alias[field] = value
    assert re.fullmatch(r"[0-9a-f]{64}", instance_key(task))
    assert instance_key(task) == instance_key(alias)


def test_signature_normalizes_visible_defaults_whitespace_and_numeric_json_only(world):
    task = world.bundle.tasks[0].model_dump(mode="json")
    alias = copy.deepcopy(task)
    alias["statement"] = " \n" + "\t  ".join(task["statement"].split()) + "\n"
    alias["figure"]["lines"][0].pop("dashed")
    alias["figure"]["lines"][0]["points"][0] = {"x": -0.0, "y": 0}
    alias["figure"]["x_min"] = int(task["figure"]["x_min"])
    assert instance_key(alias) == instance_key(task)
    first = {"statement": "2.0 + 2", "table": {"headers": [" x "], "rows": [[" 2 "]]}}
    second = {"statement": "2.0 + 2", "table": {"headers": ["x"], "rows": [["2"]]}}
    assert instance_key(first) == instance_key(second)
    second["statement"] = "2 + 2"
    assert instance_key(first) != instance_key(second)


@pytest.mark.parametrize("integer,number", [(0, -0.0), (2, 2.0)])
def test_signature_normalizes_integral_json_numbers_in_rounding(integer, number):
    snapshot = {
        "statement": "Round the result.",
        "rounding": {"digits": integer, "mode": "floor", "instruction": "Round the result."},
    }
    equivalent = copy.deepcopy(snapshot)
    equivalent["rounding"]["digits"] = number
    assert instance_key(snapshot) == instance_key(equivalent)


@pytest.mark.parametrize("field,value", [
    ("statement", "Different visible condition"), ("formula", "a+b"),
    ("table", {"headers": ["x"], "rows": [["1"]]}), ("figure", None),
    ("rounding", {"digits": 2, "mode": "floor", "instruction": "Round down."}),
])
def test_every_visible_field_contributes_to_signature(world, field, value):
    task = world.bundle.tasks[0].model_dump(mode="json")
    assert instance_key(task) != instance_key({**task, field: value})


def test_real_domain_seed_aliases_keep_provenance_but_share_instance(world):
    first = generators.generate(FAMILY, 0, world.bundle.profile)
    second = generators.generate(FAMILY, 1000, world.bundle.profile)
    assert first.id != second.id and first.generation.seed != second.generation.seed
    assert instance_key(first) == instance_key(second)


def test_historical_identity_does_not_depend_on_current_tex_allowlist(world):
    snapshot = world.bundle.tasks[0].model_dump(mode="json")
    snapshot["formula"] = r"\overrightarrow{AB}"
    with world.database.transaction(write=True) as db:
        _practice(db, world.guest, [snapshot], world.bundle.profile)
        row = _seen(db, world.guest, snapshot["id"])
        exposure = recent_exposure(db, [world.guest.id], [], NOW)
        assert row.instance_key == instance_key(snapshot)
        assert row.instance_key in exposure.keys


def test_merged_legacy_backfill_uses_original_snapshots_and_returns_actual_ids(world):
    task = world.bundle.tasks[0].model_dump(mode="json")
    first, second = ({**task, "id": "original-practice"}, {**task, "id": "original-exam"})
    at = NOW - timedelta(days=10)
    with world.database.transaction(write=True) as db:
        origin, foreign = _guest(db), _guest(db)
        account = Account(
            id=str(uuid4()), email="synthetic@example.test", root_guest_id=world.guest.id,
            role="student", created_at=at, email_verified_at=at, policy_version="test",
            consented_at=at, daily_minutes=20,
        )
        db.add(account)
        db.flush()
        db.add(GuestClaim(guest_id=origin.id, account_id=account.id, claimed_at=NOW))
        practice = _practice(db, origin, [first], world.bundle.profile, at)
        assessment = _assessment(db, world.guest, [second], world.bundle.profile, at)
        old = _seen(db, origin, first["id"], at, assistance_seen=True)
        exam_seen = _seen(db, world.guest, second["id"], at, reference_seen=True)
        unrelated = _seen(db, foreign, "foreign-only", at)
        _practice(db, foreign, [{**task, "id": "foreign-only"}], world.bundle.profile, at)
        before = copy.deepcopy((practice.tasks_snapshot, assessment.tasks_snapshot))
        original_fields = (old.id, old.guest_id, old.first_seen_at, old.last_seen_at)
        owners = world.learning.owner_ids(db, world.guest)
        current = Task.model_validate({**first, "statement": "A later edited condition"})
        exposure = recent_exposure(db, owners, [current], NOW)
        aliases = aliases_for_task(db, owners, task, tasks=[current])
        assert {first["id"], second["id"]} <= exposure.ids
        assert instance_key(task) in exposure.keys
        assert instance_key(current) not in exposure.keys
        assert aliases.ids == frozenset({task["id"], first["id"], second["id"]})
        assert {row.id for row in aliases.records} == {old.id, exam_seen.id}
        assert old.instance_key == exam_seen.instance_key == instance_key(task)
        assert unrelated.instance_key is None
        assert (old.id, old.guest_id, old.first_seen_at, old.last_seen_at) == original_fields
        assert (practice.tasks_snapshot, assessment.tasks_snapshot) == before
        assert old.assistance_seen and exam_seen.reference_seen


def test_legacy_bundle_fallback_and_unresolved_id_keep_timestamps(world):
    task = world.legacy.tasks[0]
    with world.database.transaction(write=True) as db:
        known = _seen(db, world.guest, task.id)
        unknown = _seen(db, world.guest, "missing-original")
        exposure = recent_exposure(db, [world.guest.id], world.legacy.tasks, NOW)
        assert known.instance_key == instance_key(task)
        assert unknown.instance_key is None and unknown.task_id in exposure.ids
        assert known.first_seen_at == known.last_seen_at == NOW


def test_recent_boundary_and_whole_continued_session_exclusion(world):
    old = generators.generate(FAMILY, 17, world.bundle.profile)
    recent = generators.generate(FAMILY, 18, world.bundle.profile)
    with world.database.transaction(write=True) as db:
        _seen(db, world.guest, old.id, NOW - timedelta(days=30))
        _seen(db, world.guest, recent.id, NOW - timedelta(days=30) + timedelta(seconds=1))
        _practice(db, world.guest, [old.model_dump(mode="json")], world.bundle.profile,
                  NOW - timedelta(days=40))
        exposure = recent_exposure(db, [world.guest.id], [old, recent], NOW)
        assert old.id not in exposure.ids and instance_key(old) not in exposure.keys
        assert recent.id in exposure.ids and instance_key(recent) in exposure.keys
        excluded = recent_exposure(db, [world.guest.id], [], NOW, exclude=[old.id])
        assert instance_key(old) in excluded.keys
        explicit = recent_exposure(db, [], [], NOW, exclude_tasks=[old])
        assert explicit.ids == frozenset({old.id}) and explicit.keys == {instance_key(old)}


def test_mark_instances_preserves_original_scope_flags_and_first_signature(world):
    task = world.bundle.tasks[0]
    with world.database.transaction(write=True) as db:
        origin = _guest(db)
        old = _seen(db, origin, task.id, NOW - timedelta(days=60), reference_seen=True)
        _practice(db, origin, [task.model_dump(mode="json")], world.bundle.profile,
                  NOW - timedelta(days=60))
        before = (old.id, old.guest_id, old.first_seen_at)
        changed = task.model_copy(update={"statement": "A revised visible condition"})
        rows = mark_instances(db, origin.id, [changed, changed], NOW)
        assert len(rows) == 1 and rows[0].id == old.id
        assert old.instance_key == instance_key(task)
        assert old.reference_seen and old.last_seen_at == NOW
        assert (old.id, old.guest_id, old.first_seen_at) == before
        mark_instances(db, origin.id, [changed], NOW - timedelta(seconds=1))
        assert old.last_seen_at == NOW
        assert not list(db.scalars(select(SeenTask).where(SeenTask.guest_id == world.guest.id)))


def test_new_marks_are_idempotent_and_expose_condition_aliases(world):
    task = world.bundle.tasks[0]
    alias = generators.generate(FAMILY, 1000, world.bundle.profile)
    with world.database.transaction(write=True) as db:
        first = mark_instances(db, world.guest.id, [task, alias], NOW)
        second = mark_instances(db, world.guest.id, [task, alias], NOW)
        assert [row.id for row in first] == [row.id for row in second]
        assert {row.instance_key for row in first} == {instance_key(task)}
        assert aliases_for_task(db, [world.guest.id], alias).ids == {task.id, alias.id}


def test_deterministic_sha32_seed_preserves_all_bits():
    expected = int.from_bytes(hashlib.sha256(json.dumps(
        ["runtime-v1", "owner", KEY, FAMILY, 7], separators=(",", ":"), ensure_ascii=False,
    ).encode()).digest()[:4], "big")
    assert deterministic_seed("owner", KEY, FAMILY, 7) == expected
    seeds = {deterministic_seed("owner", KEY, FAMILY, index) for index in range(64)}
    assert len(seeds) == 64 and min(seeds) < 2**31 <= max(seeds) <= 2**32 - 1
    assert deterministic_seed("other", KEY, FAMILY, 7) != expected


@pytest.mark.parametrize("source", ["demo", "legacy", "fabricated-reviewed", "static-only"])
def test_source_gates_never_activate_runtime_from_legacy_or_reviewed_looking_tasks(world, source):
    if source == "legacy":
        world.bundle = world.legacy
    elif source == "static-only":
        world.bundle = ContentBundle(world.bundle.profile, (), (
            generators.reproduce("triangle-exterior-angle", 0, world.bundle.profile),
        ))
    else:
        world.learning.settings = replace(world.learning.settings, allow_demo_content=False)
        if source == "fabricated-reviewed":
            raw = world.bundle.tasks[0].model_dump(mode="json")
            raw["review_status"] = "reviewed"
            raw["source"]["reviewed_by"] = "synthetic-unbacked-name"
            world.bundle = ContentBundle(world.bundle.profile, (), (Task.model_validate(raw),))
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db)
        assert tasks == [] and notice


def test_demo_generation_is_detached_exact_filtered_and_deterministic(world):
    before = world.bundle.tasks[0].model_dump(mode="json")
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db)
        replay, replay_notice = _generate(world, db)
        assert [task.model_dump() for task in tasks] == [task.model_dump() for task in replay]
        assert notice is replay_notice is None and len(tasks) == 5
        assert len({instance_key(task) for task in tasks}) == 5
        for task in tasks:
            a, c = map(int, re.findall(r"\d+", task.statement))
            expected = Fraction(a * isqrt(c * c - a * a), 2)
            assert Fraction(task.answer.replace(",", ".")) == expected
            assert task.id == f"course-{FAMILY}-{task.generation.seed}"
            assert task.generation.template_version == task.revision == "1"
            assert task.review_status == "demo" and task.source.reviewed_by is None
        tasks[0].hints[0] = "changed only in this returned object"
        assert tasks[0].hints != replay[0].hints
        assert world.bundle.tasks[0].model_dump(mode="json") == before


def test_only_active_published_independently_reviewed_template_authorizes_production(world):
    world.learning.settings = replace(world.learning.settings, allow_demo_content=False)
    with world.database.transaction(write=True) as db:
        revision, _, _ = _published(db, world)
        # Publication alone suffices; no reviewed-looking seed task is needed in the bundle.
        world.bundle = ContentBundle(world.bundle.profile, (), ())
        tasks, notice = _generate(world, db)
        assert len(tasks) == 5 and notice is None
        for task in tasks:
            assert task.review_status == "reviewed"
            assert task.source.author == revision.author_id
            assert task.source.reviewed_by == revision.reviewer_id
            original = generators.generate(FAMILY, task.generation.seed, world.bundle.profile)
            fields = set(Task.model_fields) - {"review_status", "source"}
            assert all(getattr(task, field) == getattr(original, field) for field in fields)
            assert task.source.rights == original.source.rights
            assert revision.id in task.source.origin


@pytest.mark.parametrize("fault", [
    "withdrawn", "not-published", "formula-unreviewed", "missing-human", "wrong-reviewer",
    "failed-run", "stale-profile", "wrong-version", "payload-tampered", "sample-tampered",
])
def test_controlled_template_failures_block_demo_fallback(world, fault):
    with world.database.transaction(write=True) as db:
        record, pointer, run = _published(db, world, reviews=9 if fault == "missing-human" else 10)
        if fault == "withdrawn":
            pointer.withdrawn = True
        elif fault == "not-published":
            record.status = "ready"
        elif fault == "formula-unreviewed":
            record.reviewed_formula = False
        elif fault == "wrong-reviewer":
            record.reviewer_id = "another-synthetic-reviewer"
        elif fault == "failed-run":
            run.passed = False
        elif fault == "stale-profile":
            run.profile_hash = "0" * 64
        elif fault == "wrong-version":
            record.payload = {**record.payload, "generator_version": "2"}
            record.payload_hash = digest(record.payload)
        elif fault == "payload-tampered":
            record.payload_hash = "0" * 64
        elif fault == "sample-tampered":
            review = db.scalar(select(TemplateHumanReview))
            review.output_snapshot = {**review.output_snapshot, "answer": "999"}
        tasks, notice = _generate(world, db, max_attempts=2)
        assert tasks == [] and notice


def test_review_evidence_without_active_publication_is_not_authority(world):
    world.learning.settings = replace(world.learning.settings, allow_demo_content=False)
    with world.database.transaction(write=True) as db:
        _published(db, world, pointer=False)
        assert _generate(world, db)[0] == []


@pytest.mark.parametrize("fault", ["manifest-list", "checks-mapping"])
def test_malformed_evidence_shape_cannot_authorize_generation(world, monkeypatch, caplog, fault):
    calls = []
    with world.database.transaction(write=True) as db:
        _, _, run = _published(db, world)
        if fault == "manifest-list":
            run.output_hashes = list(run.output_hashes)
        else:
            run.checks = dict.fromkeys(CHECKS, "PRIVATE-evidence-payload")
        monkeypatch.setattr(generators, "generate", lambda *args: calls.append(args))
        tasks, notice = _generate(world, db)
        assert tasks == [] and notice and calls == []
    assert world.learning.operation_health.snapshot()["events"]["generator"]["failures"] == 1
    logs = [row for row in caplog.records if row.name == "app.issuance"]
    assert len(logs) == 1 and logs[0].exc_info is None
    assert "PRIVATE-evidence-payload" not in caplog.text


@pytest.mark.parametrize("fault", ["editorial", "history", "history-container", "seen-key"])
def test_malformed_exclusion_data_stops_generation_with_redacted_notice(
    world, monkeypatch, caplog, fault,
):
    marker = "PRIVATE-exclusion-payload"
    calls = []
    with world.database.transaction(write=True) as db:
        if fault == "editorial":
            revision, _, _ = _published(db, world, pointer=False)
            revision.kind = "task"
            revision.content_id = "unresolved-editorial-task"
            revision.payload = {"id": revision.content_id, "statement": {"secret": marker}}
            revision.payload_hash = digest(revision.payload)
            db.add(EditorPublication(
                kind="task", content_id=revision.content_id, revision_id=revision.id,
                withdrawn=True, reason="Synthetic withdrawal", updated_at=NOW,
            ))
        elif fault in {"history", "history-container"}:
            snapshots = [marker] if fault == "history" else {}
            _practice(db, world.guest, snapshots, world.bundle.profile)
        else:
            _seen(db, world.guest, world.bundle.tasks[0].id, instance_key=marker)
        monkeypatch.setattr(generators, "generate", lambda *args: calls.append(args))
        tasks, notice = _generate(world, db)
        assert tasks == [] and notice and calls == []
        assert marker not in notice
    assert world.learning.operation_health.snapshot()["events"]["generator"]["failures"] == 1
    logs = [row for row in caplog.records if row.name == "app.issuance"]
    assert len(logs) == 1 and logs[0].exc_info is None
    assert marker not in caplog.text and KEY not in caplog.text


@pytest.mark.parametrize("block", ["tombstone", "exclusion", "published-override"])
def test_generated_id_cannot_resurrect_editorial_task(world, block):
    seed = deterministic_seed(world.guest.id, KEY, FAMILY, 0)
    task = generators.generate(FAMILY, seed, world.bundle.profile)
    with world.database.transaction(write=True) as db:
        if block == "exclusion":
            db.add(CorrectionExclusion(
                id=str(uuid4()), task_id=task.id, task_revision=task.revision,
                reason="Synthetic correction", actor_id="synthetic-editor", created_at=NOW,
            ))
        else:
            revision_id = None
            if block == "published-override":
                record, _, _ = _published(db, world, pointer=False)
                record.kind = "task"
                record.content_id = task.id
                record.payload = task.model_dump(mode="json")
                record.payload["statement"] = "Synthetic corrected condition"
                record.payload_hash = digest(record.payload)
                revision_id = record.id
            db.add(EditorPublication(
                kind="task", content_id=task.id, revision_id=revision_id,
                withdrawn=block == "tombstone", reason="Synthetic edit", updated_at=NOW,
            ))
        tasks, notice = _generate(world, db, max_attempts=1)
        assert tasks == [] and notice


def test_known_visible_aliases_and_entire_previous_batch_are_excluded(world, monkeypatch):
    original = generators.generate
    seed = deterministic_seed(world.guest.id, KEY, FAMILY, 0)
    generated = original(FAMILY, seed, world.bundle.profile)
    alias = generated.model_copy(update={"id": "historical-alias", "revision": "older"})
    with world.database.transaction(write=True) as db:
        _practice(db, world.guest, [alias.model_dump(mode="json")], world.bundle.profile,
                  NOW - timedelta(days=90))
        _seen(db, world.guest, alias.id, NOW - timedelta(days=90))
        tasks, notice = _generate(world, db, exclude=frozenset({alias.id}), max_attempts=1)
        assert tasks == [] and notice
        tasks, _ = _generate(world, db, exclude_tasks=[alias], max_attempts=1)
        assert tasks == []
        mark_instances(db, world.guest.id, [alias], NOW)
        tasks, _ = _generate(world, db, max_attempts=1)
        assert tasks == []

    def repeated(template, seed, profile):
        task = original(template, 0, profile).model_dump(mode="json")
        task["id"] = f"course-{template}-{seed}"
        task["generation"]["seed"] = seed
        return task

    monkeypatch.setattr(generators, "generate", repeated)
    # One synthetic anchor authorizes a demo generator with a one-condition domain.
    with world.database.transaction(write=True) as db:
        anchor = original(FAMILY, 1, world.bundle.profile)
        world.bundle = ContentBundle(world.bundle.profile, (), (anchor,))
        tasks, notice = _generate(world, db)
        assert len(tasks) <= 1 and notice
        assert len({instance_key(task) for task in tasks}) == len(tasks)


@pytest.mark.parametrize("field,value", [
    ("answer", 1.5), ("answer", "1/3"), ("statement", "<script>unsafe</script>"),
    ("formula", r"\includegraphics{unsafe}"), ("profile_id", "wrong-profile"),
    ("skill_ids", ["foreign-skill"]), ("slot_id", "foreign-slot"), ("family_id", "other"),
    ("rounding", {"digits": 2, "mode": "floor", "instruction": "Unstated rounding"}),
])
def test_invalid_generator_outputs_fail_closed_and_are_observed(world, monkeypatch, field, value):
    generate = generators.generate

    def invalid(template, seed, profile):
        task = generate(template, seed, profile).model_dump(mode="json")
        task[field] = value
        return task

    monkeypatch.setattr(generators, "generate", invalid)
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db, max_attempts=2)
    assert tasks == [] and notice
    assert world.learning.operation_health.snapshot()["events"]["generator"]["failures"] == 2


@pytest.mark.parametrize("fault", ["seed", "version", "review", "profile-mutation"])
def test_generation_cannot_forge_provenance_or_mutate_expected_profile(world, monkeypatch, fault):
    generate = generators.generate
    original_profile = world.bundle.profile.model_dump(mode="json")

    def invalid(template, seed, profile):
        if fault == "profile-mutation":
            profile.id = "unexpected-profile-mutation"
        task = generate(template, seed, profile).model_dump(mode="json")
        if fault == "seed":
            task["generation"]["seed"] = (seed + 1) % 2**32
        elif fault == "version":
            task["generation"]["template_version"] = "unregistered-version"
        elif fault == "review":
            task["review_status"] = "reviewed"
            task["source"]["reviewed_by"] = "unbacked-name"
        return task

    monkeypatch.setattr(generators, "generate", invalid)
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db, max_attempts=1)
        assert tasks == [] and notice
    assert world.bundle.profile.model_dump(mode="json") == original_profile
    assert world.learning.operation_health.snapshot()["events"]["generator"]["failures"] == 1


def test_request_skill_and_family_filters_are_applied_to_generated_candidates(world, monkeypatch):
    families = [family for family in generators.RUNTIME_FAMILIES if family.slot == 1]
    _synthetic_bank(world, monkeypatch, families)
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db, _request(
            family_ids=[], skill_ids=["plane-theorem-choice"],
        ))
        assert len(tasks) == 5 and notice is None
        assert {task.family_id for task in tasks} == {FAMILY}
        tasks, _ = _generate(world, db, _request(
            family_ids=["trapezoid-area"], skill_ids=["plane-theorem-choice"],
        ))
        assert tasks == []


def test_withdrawn_template_null_pointer_still_blocks_its_original_generator(world):
    with world.database.transaction(write=True) as db:
        _, pointer, _ = _published(db, world)
        pointer.withdrawn = True
        pointer.revision_id = None
        tasks, notice = _generate(world, db)
        assert tasks == [] and notice


def test_editorial_condition_exclusion_blocks_different_seed_id_aliases(world, monkeypatch):
    generate = generators.generate
    base = generate(FAMILY, 0, world.bundle.profile)
    anchor = generate(FAMILY, 1, world.bundle.profile)
    world.bundle = ContentBundle(world.bundle.profile, (), (anchor,))
    with world.database.transaction(write=True) as db:
        revision, _, _ = _published(db, world, pointer=False)
        revision.kind = "task"
        revision.content_id = "editorial-alias"
        revision.payload = {**base.model_dump(mode="json"), "id": revision.content_id}
        revision.payload_hash = digest(revision.payload)
        db.add(EditorPublication(
            kind="task", content_id=revision.content_id, revision_id=revision.id,
            withdrawn=True, reason="Synthetic withdrawn condition", updated_at=NOW,
        ))

        def aliased(template, seed, profile):
            task = base.model_dump(mode="json")
            task["id"] = f"course-{template}-{seed}"
            task["generation"]["seed"] = seed
            return task

        monkeypatch.setattr(generators, "generate", aliased)
        tasks, notice = _generate(world, db, max_attempts=1)
        assert tasks == [] and notice


def test_oracle_failure_is_redacted_and_attempt_budgets_are_global(world, monkeypatch, caplog):
    families = generators.RUNTIME_FAMILIES[:6]
    _synthetic_bank(world, monkeypatch, families)
    calls = []

    def failing(template, seed, profile):
        calls.append((template, seed))
        raise ArithmeticError("SECRET-token answer=12345 owner=private@example.test")

    monkeypatch.setattr(generators, "generate", failing)
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db, _request(
            slots=sorted({family.slot for family in families}), family_ids=[],
        ))
    assert tasks == [] and notice and len(calls) == 256
    assert max(Counter(template for template, _ in calls).values()) <= 64
    assert all(type(seed) is int and 0 <= seed <= 2**32 - 1 for _, seed in calls)
    assert world.learning.operation_health.snapshot()["events"]["generator"]["failures"] == 256
    assert "SECRET" not in caplog.text and "12345" not in caplog.text
    assert "private@example.test" not in caplog.text and KEY not in caplog.text
    assert 1 <= len([row for row in caplog.records if row.name == "app.issuance"]) <= 2


def test_difficulty_shortage_and_assessment_slot_caps_are_explicit(world, monkeypatch):
    with world.database.transaction(write=True) as db:
        tasks, notice = _generate(world, db, _request(difficulty=3))
        assert tasks == [] and notice
        families = [family for family in generators.RUNTIME_FAMILIES
                    if family.id in {FAMILY, "displacement-length", "right-prism-volume"}]
        _synthetic_bank(world, monkeypatch, families)
        tasks, notice = _generate(
            world, db, _request(slots=[1, 2, 3], family_ids=[]),
            limit=3, slot_limits={1: 1, 2: 1, 3: 1},
        )
        assert Counter(task.slot for task in tasks) == {1: 1, 2: 1, 3: 1}
        assert notice is None


@pytest.mark.parametrize("options", [
    {"max_attempts": 257}, {"max_per_template": 65}, {"limit": 21}, {"max_attempts": True},
])
def test_callers_cannot_raise_attempt_or_output_bounds(world, options):
    with world.database.transaction(write=True) as db, pytest.raises(ValueError):
        _generate(world, db, **options)


def test_core_idempotency_adapter_freezes_helper_result_before_marking_or_source_changes(world):
    class Frozen(Schema):
        tasks: list[Task]
        notice: str | None

    calls = []
    request = _request()
    with world.database.transaction(write=True) as db:
        def action():
            tasks, notice = _generate(world, db)
            calls.append(True)
            _practice(db, world.guest, [task.model_dump(mode="json") for task in tasks],
                      world.bundle.profile)
            mark_instances(db, world.guest.id, tasks, NOW)
            return Frozen(tasks=tasks, notice=notice)

        first = world.learning._idempotent(db, world.guest, KEY, "helper-contract", request, action)
    world.bundle = ContentBundle(world.bundle.profile, (), ())
    with world.database.transaction(write=True) as db:
        db.add(EditorPublication(
            kind="template", content_id=FAMILY, revision_id=None, withdrawn=True,
            reason="Synthetic later withdrawal", updated_at=NOW,
        ))
        replay = world.learning._idempotent(
            db, world.guest, KEY, "helper-contract", request, action,
        )
        assert replay == first and calls == [True]
        assert len(list(db.scalars(select(SeenTask)))) == 5


def test_additive_migration_preserves_populated_legacy_rows_and_snapshots(tmp_path, legacy_dir):
    path = tmp_path / "populated-migration.sqlite3"
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option(
        "script_location", str(Path(__file__).resolve().parents[1] / "migrations"),
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path.as_posix()}")
    command.upgrade(config, "0006_practice_options")
    database = Database(Settings(
        database_url=f"sqlite:///{path.as_posix()}", content_dir=legacy_dir,
    ))
    try:
        legacy = load_content(legacy_dir)
        with database.transaction(write=True) as db:
            guest = _guest(db)
            snapshot = legacy.tasks[0].model_dump(mode="json")
            session = _practice(db, guest, [snapshot], legacy.profile)
            assessment = _assessment(db, guest, [snapshot], legacy.profile)
            db.execute(text(
                "INSERT INTO seen_tasks (id, guest_id, task_id, first_seen_at, last_seen_at, "
                "assistance_seen, reference_seen) VALUES (:id, :owner, :task, :at, :at, 1, 0)"
            ), {"id": "legacy-seen", "owner": guest.id, "task": snapshot["id"],
                "at": "2026-11-05 12:00:00.000000"})
            db.flush()
            before = tuple(db.execute(text("SELECT * FROM seen_tasks")).one())
            frozen = copy.deepcopy(session.tasks_snapshot)
        command.upgrade(config, "0007_instance_exposures")
        with database.transaction(write=True) as db:
            row = db.get(SeenTask, "legacy-seen")
            assert row.instance_key is None
            assert tuple(db.execute(text("SELECT * FROM seen_tasks")).one())[:-1] == before
            assert db.get(LearningSessionRecord, session.id).tasks_snapshot == frozen
            assert db.get(AssessmentRecord, assessment.id).tasks_snapshot == frozen
            recent_exposure(db, [guest.id], legacy.tasks, NOW)
            assert row.instance_key == instance_key(snapshot)
            assert tuple(db.execute(text("SELECT * FROM seen_tasks")).one())[:-1] == before
        with database.transaction() as db:
            assert db.get(SeenTask, "legacy-seen").instance_key == instance_key(snapshot)
        indexes = inspect(database.engine).get_indexes("seen_tasks")
        assert any(item["column_names"] == ["guest_id", "instance_key"] for item in indexes)
    finally:
        database.dispose()


def _track_repeat_generator(monkeypatch):
    generate = generators.generate
    calls = []

    def tracked(template, seed, profile):
        calls.append((template, seed))
        return generate(template, seed, profile)

    monkeypatch.setattr(generators, "generate", tracked)
    return calls


@pytest.mark.parametrize("as_task", [False, True])
def test_historical_repeat_reconstructs_owned_snapshot_without_writes(world, monkeypatch, as_task):
    historical = generators.generate(FAMILY, 1000, world.bundle.profile)
    assert historical.id not in {task.id for task in world.bundle.tasks}
    # A different static ID has the same condition: an explicit repeat is still allowed.
    assert instance_key(historical) == instance_key(world.bundle.tasks[0])
    with world.database.transaction(write=True) as db:
        record = _practice(
            db, world.guest, [historical.model_dump(mode="json")], world.bundle.profile,
        )
        seen = _seen(db, world.guest, historical.id, assistance_seen=True)
        db.flush()
        owner = db.scalar(select(Guest).where(Guest.id == world.guest.id).with_for_update())
        lock_catalog(db)
        owned = db.scalar(select(LearningSessionRecord).where(
            LearningSessionRecord.id == record.id, LearningSessionRecord.guest_id == owner.id,
        ))
        assert owned is record  # The caller verifies the frozen snapshot's owner.
        frozen = copy.deepcopy(owned.tasks_snapshot)
        snapshot = Task.model_validate(frozen[0]) if as_task else owned.tasks_snapshot[0]
        before = db.scalar(text("SELECT total_changes()"))
        seen.reference_seen = True  # This read must not autoflush pending caller work.
        calls = _track_repeat_generator(monkeypatch)

        repeated = historical_repeat_candidate(world.learning, db, snapshot, world.bundle)

        assert repeated is not None and repeated.model_dump() == historical.model_dump()
        assert calls == [(FAMILY, 1000)]
        assert db.scalar(text("SELECT total_changes()")) == before
        assert seen in db.dirty and seen.instance_key is None
        assert db.scalar(text("SELECT reference_seen FROM seen_tasks WHERE id = :id"),
                         {"id": seen.id}) == 0
        assert owned.tasks_snapshot == frozen
        assert seen.first_seen_at == seen.last_seen_at == NOW and seen.assistance_seen
        repeated.hints[0] = "Only the returned task changes."
        assert owned.tasks_snapshot == frozen and historical.hints[0] != repeated.hints[0]
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == 1 and events["failures"] == 0


@pytest.mark.parametrize("gate", [
    "demo-disabled", "forged-reviewed", "snapshot-only", "reviewed-anchor",
    "withdrawn-template", "invalid-publication",
])
def test_historical_repeat_requires_a_current_source_without_counting_gate_denials(
    world, monkeypatch, gate,
):
    frozen = generators.generate(FAMILY, 1007, world.bundle.profile).model_dump(mode="json")
    with world.database.transaction(write=True) as db:
        if gate in {"demo-disabled", "forged-reviewed"}:
            world.learning.settings = replace(world.learning.settings, allow_demo_content=False)
        if gate in {"forged-reviewed", "reviewed-anchor"}:
            frozen["review_status"] = "reviewed"
            frozen["source"]["reviewed_by"] = "unbacked-historical-reviewer"
        if gate == "snapshot-only":
            world.bundle = ContentBundle(world.bundle.profile, (), ())
        elif gate == "reviewed-anchor":
            anchor = world.bundle.tasks[0].model_dump(mode="json")
            anchor["review_status"] = "reviewed"
            anchor["source"]["reviewed_by"] = "unbacked-anchor-reviewer"
            world.bundle = ContentBundle(world.bundle.profile, (), (Task.model_validate(anchor),))
        elif gate == "withdrawn-template":
            _, pointer, _ = _published(db, world)
            pointer.withdrawn, pointer.revision_id = True, None
        elif gate == "invalid-publication":
            _published(db, world, reviews=9)
        db.flush()
        lock_catalog(db)
        calls = _track_repeat_generator(monkeypatch)
        assert historical_repeat_candidate(world.learning, db, frozen, world.bundle) is None
        assert calls == []
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == events["failures"] == 0


@pytest.mark.parametrize("reviewed_history", [False, True])
def test_historical_repeat_uses_current_independent_publication_attribution(
    world, monkeypatch, reviewed_history,
):
    frozen = generators.generate(FAMILY, 2**32 - 1, world.bundle.profile).model_dump(mode="json")
    if reviewed_history:
        frozen["review_status"] = "reviewed"
        frozen["source"]["author"] = "previous-template-author"
        frozen["source"]["reviewed_by"] = "previous-template-reviewer"
    before = copy.deepcopy(frozen)
    world.learning.settings = replace(world.learning.settings, allow_demo_content=False)
    with world.database.transaction(write=True) as db:
        revision, _, _ = _published(db, world)
        world.bundle = ContentBundle(world.bundle.profile, (), ())
        lock_catalog(db)
        calls = _track_repeat_generator(monkeypatch)
        repeated = historical_repeat_candidate(world.learning, db, frozen, world.bundle, now=NOW)
        assert repeated is not None and repeated.review_status == "reviewed"
        assert repeated.source.author == revision.author_id
        assert repeated.source.reviewed_by == revision.reviewer_id
        assert revision.id in repeated.source.origin
        assert repeated.id == frozen["id"]
        assert repeated.generation.model_dump() == frozen["generation"]
        assert repeated.model_dump(exclude={"source", "review_status"}) == {
            key: value for key, value in frozen.items() if key not in {"source", "review_status"}
        }
        assert calls == [(FAMILY, 2**32 - 1)] and frozen == before
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == 1 and events["failures"] == 0


def test_historical_repeat_does_not_carry_forged_review_metadata_into_demo(world):
    frozen = generators.generate(FAMILY, 1007, world.bundle.profile).model_dump(mode="json")
    frozen["review_status"] = "reviewed"
    frozen["source"]["reviewed_by"] = "unbacked-historical-reviewer"
    with world.database.transaction(write=True) as db:
        lock_catalog(db)
        repeated = historical_repeat_candidate(world.learning, db, frozen, world.bundle)
        assert repeated is not None and repeated.review_status == "demo"
        assert repeated.source.reviewed_by is None
        assert frozen["source"]["reviewed_by"] == "unbacked-historical-reviewer"


@pytest.mark.parametrize("fault", [
    "version", "revision", "profile", "slot", "slot-id", "skills", "unknown-template",
    "static-only", "id", "invalid-answer", "invalid-seed",
])
def test_historical_repeat_rejects_stale_or_invalid_binding_before_generation(
    world, monkeypatch, fault,
):
    frozen = generators.generate(FAMILY, 1007, world.bundle.profile).model_dump(mode="json")
    if fault == "version":
        frozen["generation"]["template_version"] = "2"
    elif fault == "revision":
        frozen["revision"] = "2"
    elif fault == "profile":
        frozen["profile_id"] = "retired-profile"
    elif fault == "slot":
        frozen["slot"] = 2
    elif fault == "slot-id":
        frozen["slot_id"] = "retired-slot"
    elif fault == "skills":
        frozen["skill_ids"] = ["retired-skill"]
    elif fault == "unknown-template":
        frozen["generation"]["template_id"] = "unregistered-template"
    elif fault == "static-only":
        frozen = generators.reproduce(
            "triangle-exterior-angle", 1007, world.bundle.profile,
        ).model_dump(mode="json")
    elif fault == "id":
        frozen["id"] = "rewritten-generation-id"
    elif fault == "invalid-answer":
        frozen["answer"] = 1.5
    elif fault == "invalid-seed":
        frozen["generation"]["seed"] = True
    with world.database.transaction(write=True) as db:
        lock_catalog(db)
        calls = _track_repeat_generator(monkeypatch)
        assert historical_repeat_candidate(world.learning, db, frozen, world.bundle) is None
        assert calls == []
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == events["failures"] == 0


@pytest.mark.parametrize("field", [
    "statement", "formula", "table", "figure", "rounding", "answer", "hints", "solution",
])
def test_historical_repeat_requires_exact_frozen_condition_grading_and_help(
    world, monkeypatch, caplog, field,
):
    frozen = generators.generate(FAMILY, 1007, world.bundle.profile).model_dump(mode="json")
    values = {
        "statement": frozen["statement"] + "  ",
        "formula": "a+b",
        "table": {"headers": ["x"], "rows": [["1"]]},
        "figure": None,
        "rounding": {"digits": 0, "mode": "floor", "instruction": frozen["statement"]},
        "answer": "999999",
        "hints": ["PRIVATE-replay-hint", *frozen["hints"][1:]],
        "solution": ["PRIVATE-replay-solution"],
    }
    frozen[field] = values[field]
    Task.model_validate(frozen)  # Valid shape does not prove reproducibility.
    before = copy.deepcopy(frozen)
    with world.database.transaction(write=True) as db:
        lock_catalog(db)
        calls = _track_repeat_generator(monkeypatch)
        assert historical_repeat_candidate(world.learning, db, frozen, world.bundle) is None
        assert calls == [(FAMILY, 1007)] and frozen == before
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == 0 and events["failures"] == 1
    logs = [row for row in caplog.records if row.name == "app.issuance"]
    assert len(logs) == 1 and logs[0].exc_info is None
    assert "PRIVATE-replay" not in caplog.text and frozen["id"] not in caplog.text


@pytest.mark.parametrize("fault", ["exception", "invalid-output", "profile-mutation"])
def test_historical_repeat_counts_only_its_single_failed_attempt(world, monkeypatch, caplog, fault):
    generate = generators.generate
    frozen = generate(FAMILY, 1007, world.bundle.profile)
    profile_before = world.bundle.profile.model_dump(mode="json")
    calls = []

    def failing(template, seed, profile):
        calls.append((template, seed))
        if fault == "exception":
            raise ArithmeticError("PRIVATE-repeat-token answer=999999")
        if fault == "profile-mutation":
            profile.id = "unexpected-profile"
        task = generate(template, seed, profile).model_dump(mode="json")
        if fault == "invalid-output":
            task["answer"] = 1.5
        return task

    monkeypatch.setattr(generators, "generate", failing)
    with world.database.transaction(write=True) as db:
        lock_catalog(db)
        assert historical_repeat_candidate(world.learning, db, frozen, world.bundle) is None
    assert calls == [(FAMILY, 1007)]
    assert world.bundle.profile.model_dump(mode="json") == profile_before
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == 0 and events["failures"] == 1
    logs = [row for row in caplog.records if row.name == "app.issuance"]
    assert len(logs) == 1 and logs[0].exc_info is None
    assert "PRIVATE-repeat-token" not in caplog.text and "999999" not in caplog.text


@pytest.mark.parametrize("block", [
    "exclusion-id", "tombstone-id", "override-id", "bundle-alias", "editorial-alias",
    "corrected-alias-base", "malformed-exclusion",
])
def test_historical_repeat_respects_task_corrections_tombstones_and_alias_keys(
    world, monkeypatch, block,
):
    frozen = generators.generate(FAMILY, 1000, world.bundle.profile)
    with world.database.transaction(write=True) as db:
        if block in {"exclusion-id", "bundle-alias"}:
            identifier = frozen.id if block == "exclusion-id" else world.bundle.tasks[0].id
            db.add(CorrectionExclusion(
                id=str(uuid4()), task_id=identifier, task_revision="earlier-revision",
                reason="Synthetic correction", actor_id="synthetic-editor", created_at=NOW,
            ))
        elif block == "tombstone-id":
            db.add(EditorPublication(
                kind="task", content_id=frozen.id, revision_id=None, withdrawn=True,
                reason="Synthetic withdrawal", updated_at=NOW,
            ))
        else:
            identifier = frozen.id if block == "override-id" else "historical-editorial-alias"
            payload = {**frozen.model_dump(mode="json"), "id": identifier}
            base = copy.deepcopy(payload) if block == "corrected-alias-base" else None
            if block in {"override-id", "corrected-alias-base"}:
                payload["statement"] = "Synthetic corrected condition."
            elif block == "malformed-exclusion":
                payload["statement"] = {"private": "PRIVATE-invalid-exclusion"}
            revision = EditorRevision(
                id=str(uuid4()), kind="task", content_id=identifier, version=1, revision=4,
                status="published", title="Synthetic task correction", payload=payload,
                payload_hash=digest(payload), base_snapshot=base, parent_id=None,
                author_id="synthetic-author", reviewer_id="synthetic-reviewer",
                change_note="Synthetic test data", review_note="Synthetic test review",
                reviewed_formula=True, reviewed_constraints=True, created_at=NOW,
                updated_at=NOW, reviewed_at=NOW, published_at=NOW,
            )
            db.add(revision)
            db.flush()
            db.add(EditorPublication(
                kind="task", content_id=identifier, revision_id=revision.id,
                withdrawn=block != "override-id", reason="Synthetic correction", updated_at=NOW,
            ))
        db.flush()
        lock_catalog(db)
        before = db.scalar(text("SELECT total_changes()"))
        calls = _track_repeat_generator(monkeypatch)
        assert historical_repeat_candidate(world.learning, db, frozen, world.bundle) is None
        assert calls == [] and db.scalar(text("SELECT total_changes()")) == before
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == events["failures"] == 0


@pytest.mark.parametrize("edited", [False, True])
def test_historical_repeat_defers_current_bundle_ids_to_static_selection(
    world, monkeypatch, edited,
):
    frozen = world.bundle.tasks[0].model_dump(mode="json")
    if edited:
        task = world.bundle.tasks[0].model_copy(update={"statement": "A current edited condition."})
        world.bundle = ContentBundle(world.bundle.profile, (), (task,))
    with world.database.transaction(write=True) as db:
        lock_catalog(db)
        calls = _track_repeat_generator(monkeypatch)
        assert historical_repeat_candidate(world.learning, db, frozen, world.bundle) is None
        assert calls == []
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == events["failures"] == 0


def test_historical_repeat_uses_supplied_time_for_publication_gate(world, monkeypatch):
    frozen = generators.generate(FAMILY, 1007, world.bundle.profile)
    world.learning.settings = replace(world.learning.settings, allow_demo_content=False)
    with world.database.transaction(write=True) as db:
        _published(db, world)
        lock_catalog(db)
        calls = _track_repeat_generator(monkeypatch)
        assert historical_repeat_candidate(
            world.learning, db, frozen, world.bundle, now=NOW - timedelta(days=1),
        ) is None
        assert calls == []
    events = world.learning.operation_health.snapshot()["events"]["generator"]
    assert events["successes"] == events["failures"] == 0
