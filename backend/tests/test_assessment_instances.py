"""Assessment integration through the actual app and isolated immutable histories."""

import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app import generators
from app.accounts.models import AccessSession
from app.assessments.evidence import released_evidence
from app.assessments.models import AssessmentRecord
from app.content import load_content
from app.editor.models import EditorCatalog, EditorPublication
from app.instances import instance_key
from app.issuance import generate_candidates
from app.models import AttemptRecord, Guest, IdempotencyRecord, LearningSessionRecord, SeenTask
from tests.helpers import answer, key, start
from tests.test_account_expiry import _advance_after_row_lock
from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory
from tests.test_assessments import activate, finalize, prepare, save, takeover, view
from tests.test_assessments import single_slot_bank as single_slot_bank


def _rows(database, *models):
    with database.engine.connect() as connection:
        return {
            model.__tablename__: [dict(row) for row in connection.execute(
                select(model.__table__).order_by(*model.__table__.primary_key.columns),
            ).mappings()]
            for model in models
        }


def _record(client, assessment):
    with client.app.state.database.transaction() as db:
        record = db.get(AssessmentRecord, assessment["id"])
        assert record is not None
        return {column.name: deepcopy(getattr(record, column.name))
                for column in AssessmentRecord.__table__.columns}


def _answers(client, assessment):
    return {task["id"]: {"answer": task["answer"], "active_seconds": 10}
            for task in _record(client, assessment)["tasks_snapshot"]}


def _write_tasks(content_dir, tasks):
    (content_dir / "tasks.json").write_text(
        json.dumps(tasks, ensure_ascii=False), encoding="utf-8",
    )


def _alias(content_dir, original, identifier="synthetic-assessment-alias"):
    """Replace the isolated current bank; issued snapshots retain their old IDs."""
    alias = {**original.model_dump(mode="json"), "id": identifier, "revision": "alias-2"}
    tasks = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))
    _write_tasks(content_dir, [alias if task["id"] == original.id else task for task in tasks])
    return alias


def _runtime_bank(content_dir, content, slots):
    families = {}
    for family in generators.RUNTIME_FAMILIES:
        families.setdefault(family.slot, family)
    anchors = [generators.generate(families[slot].id, 0, content.profile) for slot in slots]
    _write_tasks(content_dir, [
        *(task.model_dump(mode="json") for task in anchors),
        *(task.model_dump(mode="json") for task in content.tasks if task.slot not in slots),
    ])
    return anchors


@pytest.mark.parametrize("missing", [(1, 3), tuple(range(1, 14))], ids=["two-slots", "all-13"])
def test_runtime_depletion_uses_one_bounded_call_and_replays_after_withdrawal(
    client_factory, content_dir, content, clock, monkeypatch, missing,
):
    anchors = _runtime_bank(content_dir, content, missing)
    client = client_factory()
    owner = client.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    first_response = prepare(client, device=device)
    assert first_response.status_code == 200, first_response.text
    first = first_response.json()
    original = _record(client, first)
    original_exposures = _rows(client.app.state.database, SeenTask)
    calls = []

    def observed(learning, db, guest, request, request_key, bundle, **options):
        calls.append((request, request_key, deepcopy(options)))
        return generate_candidates(learning, db, guest, request, request_key, bundle, **options)

    monkeypatch.setattr("app.assessments.service.generate_candidates", observed, raising=False)
    clock[0] += timedelta(seconds=1)
    headers = {"Idempotency-Key": "ABCDEFAB-1234-4567-89AB-ABCDEF123456"}
    second_response = prepare(client, device=device, headers=headers)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert len(calls) == 1
    request, request_key, options = calls[0]
    assert request_key == headers["Idempotency-Key"].lower()
    assert set(request.slots) == set(missing)
    assert request.length in {5, 10, 20}
    assert options["slot_limits"] == dict.fromkeys(missing, 1)
    assert options["limit"] == len(missing) <= 13
    excluded = options["exclude_tasks"]
    assert {task.slot for task in excluded} == set(range(1, 14)) - set(missing)
    assert all(task.answer and task.solution for task in excluded)
    assert not ({instance_key(task) for task in first["tasks"]}
                & {instance_key(task) for task in second["tasks"]})
    assert len(second["tasks"]) == len({instance_key(task) for task in second["tasks"]}) == 13
    assert {task["slot"] for task in second["tasks"]} == set(range(1, 14))
    assert second["status"] == "prepared"
    assert second["started_at"] is second["deadline_at"] is None
    assert second["server_result"] is second["local_result"] is None
    assert all(not {"answer", "solution", "hints", "generation", "source", "instance_key"}
               & task.keys() for task in second["tasks"])
    frozen = _record(client, second)
    for task in frozen["tasks_snapshot"]:
        if task["slot"] in missing:
            provenance = task["generation"]
            assert task == generators.generate(
                provenance["template_id"], provenance["seed"], content.profile,
            ).model_dump(mode="json")
    with client.app.state.database.transaction() as db:
        exposures = list(db.scalars(select(SeenTask)))
        assert len(exposures) == 26
        assert {item.guest_id for item in exposures} == {owner}
        assert {item.instance_key for item in exposures} == {
            instance_key(task) for task in [*first["tasks"], *second["tasks"]]
        }
    current = _rows(client.app.state.database, SeenTask)["seen_tasks"]
    assert [row for row in current if row["task_id"] in {
        task["id"] for task in first["tasks"]
    }] == original_exposures["seen_tasks"]
    assert _record(client, first) == original

    with client.app.state.database.transaction(write=True) as db:
        for anchor in anchors:
            db.add(EditorPublication(
                kind="template", content_id=anchor.family_id, revision_id=None, withdrawn=True,
                reason="Synthetic withdrawal fixture", updated_at=clock[0],
            ))

    def unexpected(*args, **kwargs):
        pytest.fail("durable assessment replay must precede catalog access and generation")

    with monkeypatch.context() as patch:
        patch.setattr(client.app.state.service, "locked_content", unexpected)
        patch.setattr(generators, "generate", unexpected)
        replay = prepare(client, device=device, headers={
            "Idempotency-Key": headers["Idempotency-Key"].lower(),
        })
    assert replay.content == second_response.content
    assert len(calls) == 1
    assert _record(client, second) == frozen
    assert view(client, second, device).json()["tasks"] == second["tasks"]
    repeated = prepare(client, device=device)
    assert repeated.status_code == 200, repeated.text
    assert "повтор" in repeated.json()["result_notice"].lower()


def test_partial_runtime_shortage_rolls_back_selection_and_legacy_key_backfill(
    client_factory, content_dir, content, clock, monkeypatch,
):
    anchors = _runtime_bank(content_dir, content, (1,))
    client = client_factory()
    client.post("/api/v1/guest", json={})
    practice = start(client, slots=[1])
    assert practice.status_code == 200, practice.text
    database = client.app.state.database
    with database.transaction(write=True) as db:
        seen = db.scalars(select(SeenTask).where(SeenTask.task_id == anchors[0].id)).one()
        seen.instance_key = None
    tasks = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))
    _write_tasks(content_dir, [task for task in tasks if task["slot"] != 13])
    before = _rows(database, AssessmentRecord, SeenTask, LearningSessionRecord, AttemptRecord)
    generated = []

    def observed(*args, **kwargs):
        selected, notice = generate_candidates(*args, **kwargs)
        generated.extend(selected)
        return selected, notice

    monkeypatch.setattr("app.assessments.service.generate_candidates", observed, raising=False)
    clock[0] += timedelta(seconds=1)
    headers, device = key(), str(uuid4())
    response = prepare(client, device=device, headers=headers)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "assessment_bank_incomplete"
    assert "13" in response.json()["error"]["message"]
    assert generated and {task.slot for task in generated} == {1}
    assert _rows(
        database, AssessmentRecord, SeenTask, LearningSessionRecord, AttemptRecord,
    ) == before
    counters = client.app.state.operation_health.snapshot()["events"]
    assert prepare(client, device=device, headers=headers).content == response.content
    assert client.app.state.operation_health.snapshot()["events"] == counters
    with database.transaction() as db:
        stored = db.scalars(select(IdempotencyRecord).where(
            IdempotencyRecord.request_key == headers["Idempotency-Key"],
        )).one()
        assert stored.status_code == 409


def test_thirteen_ids_with_only_twelve_conditions_fail_atomically(
    client_factory, content_dir, single_slot_bank,
):
    tasks = [task.model_dump(mode="json") for task in single_slot_bank.tasks]
    source = next(task for task in tasks if task["slot"] == 12)
    duplicate = next(task for task in tasks if task["slot"] == 13)
    for field in ("statement", "formula", "table", "figure", "rounding"):
        duplicate[field] = source.get(field)
    _write_tasks(content_dir, tasks)
    client = client_factory()
    client.post("/api/v1/guest", json={})
    response = prepare(client)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "assessment_bank_incomplete"
    assert _rows(client.app.state.database, AssessmentRecord, SeenTask) == {
        "assessments": [], "seen_tasks": [],
    }


def test_historical_static_fallback_is_labelled_without_second_independent_credit(
    client_factory, single_slot_bank,
):
    client = client_factory()
    client.post("/api/v1/guest", json={})
    device = str(uuid4())
    first = prepare(client, device=device).json()
    assert activate(client, first, device).status_code == 200
    result = finalize(client, first, device, _answers(client, first)).json()["server_result"]
    assert result["independent_total"] == 13
    repeated = prepare(client, device=device)
    assert repeated.status_code == 200, repeated.text
    second = repeated.json()
    assert "повтор" in second["result_notice"].lower()
    assert second["tasks"] == first["tasks"]
    assert activate(client, second, device).status_code == 200
    completed = finalize(client, second, device, _answers(client, second))
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    assert result["score"] == result["assisted_total"] == 13
    assert result["independent_total"] == 0


@pytest.mark.parametrize("completion", ["online", "deadline"])
@pytest.mark.parametrize("exposure", ["before-input", "after-input"])
@pytest.mark.parametrize("help_kind", ["hint", "solution", "reference"])
def test_alias_help_uses_frozen_conditions_and_preserves_first_input(
    client_factory, content_dir, single_slot_bank, clock, completion, exposure, help_kind,
):
    client = client_factory()
    owner = client.post("/api/v1/guest", json={}).json()["id"]
    practice = start(client, slots=[1]).json()
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    assert practice["tasks"][0]["id"] == original.id
    alias = _alias(content_dir, original)
    device = str(uuid4())
    prepared = prepare(client, device=device, duration_minutes=15)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()
    assert assessment["tasks"][0]["id"] == alias["id"]
    active = activate(client, assessment, device).json()
    # Change today's condition after preparation. Eligibility must use the
    # original practice snapshot and the assessment's frozen alias instead.
    current = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))
    for task in current:
        if task["id"] == alias["id"]:
            task["statement"] = "Synthetic revised condition: find 37."
    _write_tasks(content_dir, current)

    def help_request():
        if help_kind == "reference":
            return answer(client, practice, practice["tasks"][0], "", skipped=True)
        suffix = "hints" if help_kind == "hint" else "solution"
        return client.post(f"/api/v1/sessions/{practice['id']}/{suffix}", json={
            "task_id": original.id, **({"level": 1} if help_kind == "hint" else {}),
        })

    if exposure == "before-input":
        assert help_request().status_code == 200
    clock[0] += timedelta(seconds=1)
    intermediate = {"answer": "−", "active_seconds": 2}
    first_draft = {**intermediate, "recorded_at": clock[0].isoformat()}
    assert save(client, assessment, device, {alias["id"]: intermediate}).status_code == 200
    clock[0] += timedelta(seconds=1)
    first = {"answer": "999999", "active_seconds": 3}
    first_answer = {**first, "recorded_at": clock[0].isoformat()}
    assert save(client, assessment, device, {alias["id"]: first}, revision=1).status_code == 200
    context = _record(client, assessment)["answer_context"][alias["id"]]
    assert context == {
        "assisted": exposure == "before-input", "first_answer": first_answer, "owner_ids": [owner],
    }
    if exposure == "after-input":
        clock[0] += timedelta(seconds=1)
        assert help_request().status_code == 200
    clock[0] += timedelta(seconds=1)
    answers = _answers(client, assessment)
    assert save(client, assessment, device, answers, revision=2).status_code == 200
    if completion == "deadline":
        clock[0] = datetime.fromisoformat(active["deadline_at"])
        assert client.app.state.assessments.reconcile_deadlines() == 1
        pending = view(client, assessment, device).json()
        assert pending["server_result"] is pending["local_result"] is None
        with client.app.state.database.transaction() as db:
            assert released_evidence(db, [owner]) == []
        frozen = _record(client, assessment)["server_result"]
        clock[0] += timedelta(seconds=1)
    completed = finalize(client, assessment, device, answers, lost=completion == "deadline")
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    row = result["rows"][0]
    assert row["task_id"] == alias["id"] and row["correct"] is True
    assert row["assisted"] is True and row["independent"] is False
    assert row["first_draft"] == first_draft and row["first_answer"] == first_answer
    assert result["independent_total"] == 12
    assert _record(client, assessment)["answer_context"][alias["id"]] == context
    if completion == "deadline":
        assert result == frozen
        assert completed.json()["local_result"]["independent_total"] == 0
    with client.app.state.database.transaction() as db:
        evidence = released_evidence(db, [owner])
        assert len(evidence) == 13 and evidence[0]["id"] == row["id"]
        assert evidence[0]["first_answer"] == first_answer
        historical = db.get(LearningSessionRecord, practice["id"])
        assert historical.tasks_snapshot == [original.model_dump(mode="json")]


@pytest.mark.parametrize("completion", ["online", "deadline"])
@pytest.mark.parametrize("source", ["practice", "pending-server"])
def test_prior_numeric_aliases_reserve_canonical_credit(
    client_factory, content_dir, single_slot_bank, clock, source, completion,
):
    client = client_factory()
    owner = client.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    if source == "practice":
        practice = start(client, slots=[1]).json()
        previous = answer(client, practice, practice["tasks"][0], original.answer)
        assert previous.status_code == 200, previous.text
        history = _rows(client.app.state.database, AttemptRecord, LearningSessionRecord)
    else:
        previous = prepare(client, device=device, duration_minutes=15).json()
        active = activate(client, previous, device).json()
        assert save(client, previous, device, {
            original.id: {"answer": original.answer, "active_seconds": 3},
        }).status_code == 200
        clock[0] = datetime.fromisoformat(active["deadline_at"])
        assert client.app.state.assessments.reconcile_deadlines() == 1
        history = _record(client, previous)
        assert history["server_result"]["independent_total"] == 1
        assert view(client, previous).json()["server_result"] is None
        with client.app.state.database.transaction() as db:
            assert released_evidence(db, [owner]) == []
    alias = _alias(content_dir, original)
    clock[0] += timedelta(seconds=1)
    assessment = prepare(client, device=device, duration_minutes=15).json()
    assert assessment["tasks"][0]["id"] == alias["id"]
    active = activate(client, assessment, device).json()
    answers = _answers(client, assessment)
    assert save(client, assessment, device, answers).status_code == 200
    if completion == "deadline":
        clock[0] = datetime.fromisoformat(active["deadline_at"])
        assert client.app.state.assessments.reconcile_deadlines() == 1
    completed = finalize(client, assessment, device, answers, lost=completion == "deadline")
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    assert result["independent_total"] == 12
    assert result["rows"][0]["independent"] is False
    assert result["rows"][0]["assisted"] is (source == "practice")
    if source == "practice":
        assert _rows(client.app.state.database, AttemptRecord, LearningSessionRecord) == history
    else:
        assert _record(client, previous) == history


def test_preparation_and_release_preserve_merged_origins_exposure_rows(
    account_factory, account_config, content_dir, single_slot_bank, clock,
):
    mailbox = Mailbox()
    root = account_factory(config=account_config, mailbox=mailbox)
    root.post("/api/v1/guest", json={})
    account = login(root, mailbox)
    root_id = account["root_guest_id"]
    origin = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=root.app.state.settings.database_url,
    )
    origin_id = origin.post("/api/v1/guest", json={}).json()["id"]
    practice = start(origin, slots=[1]).json()
    task_id = practice["tasks"][0]["id"]
    assert origin.post(f"/api/v1/sessions/{practice['id']}/hints", json={
        "task_id": task_id, "level": 1,
    }).status_code == 200
    device = str(uuid4())
    historical = prepare(origin, device=device, mode="diagnostic").json()
    assert activate(origin, historical, device).status_code == 200
    assert save(origin, historical, device, {
        task_id: {"answer": "999999", "active_seconds": 2},
    }).status_code == 200
    frozen_input = _record(origin, historical)
    database = root.app.state.database
    # Synthetic pre-0007 exposure: only this nullable identity field may be filled.
    with database.transaction(write=True) as db:
        db.scalars(select(SeenTask).where(
            SeenTask.guest_id == origin_id, SeenTask.task_id == task_id,
        )).one().instance_key = None
    before = _rows(database, SeenTask)["seen_tasks"]
    assert {row["guest_id"] for row in before} == {origin_id}
    practice_history = _rows(database, LearningSessionRecord, AttemptRecord)
    clock[0] += timedelta(seconds=1)
    assert set(login(origin, mailbox)["owner_ids"]) == {*account["owner_ids"], origin_id}
    clock[0] += timedelta(seconds=1)
    prepared = prepare(root, device=device)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()
    assert _record(root, assessment)["guest_id"] == root_id
    assert activate(root, assessment, device).status_code == 200
    result = finalize(root, assessment, device, _answers(root, assessment))
    assert result.status_code == 200, result.text
    assert result.json()["server_result"]["independent_total"] == 12
    after = _rows(database, SeenTask)["seen_tasks"]
    preserved = [row for row in after if row["guest_id"] == origin_id]
    expected = deepcopy(before)
    for row in expected:
        if row["task_id"] == task_id:
            row["instance_key"] = instance_key(practice["tasks"][0])
    assert preserved == expected
    own = [row for row in after if row["guest_id"] == root_id]
    assert len(own) == 13 and all(row["reference_seen"] for row in own)
    assert {row["id"] for row in own}.isdisjoint(row["id"] for row in preserved)
    assert _record(origin, historical) == frozen_input
    assert _rows(database, LearningSessionRecord, AttemptRecord) == practice_history


def test_pending_alias_reservation_survives_merge_and_late_local_has_no_second_evidence(
    account_factory, account_config, content_dir, single_slot_bank, clock,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    first_owner = first.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    source = prepare(first, device=device, duration_minutes=15).json()
    active = activate(first, source, device).json()
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    first_input = {"answer": "999999", "active_seconds": 2}
    assert save(first, source, device, {original.id: first_input}).status_code == 200
    clock[0] += timedelta(seconds=1)
    assert save(first, source, device, {
        original.id: {"answer": original.answer, "active_seconds": 4},
    }, revision=1).status_code == 200
    clock[0] = datetime.fromisoformat(active["deadline_at"])
    assert first.app.state.assessments.reconcile_deadlines() == 1
    frozen = _record(first, source)
    assert frozen["server_result"]["score"] == frozen["server_result"]["independent_total"] == 1
    account = login(first, mailbox)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    second_owner = second.post("/api/v1/guest", json={}).json()["id"]
    alias = _alias(content_dir, original)
    assessment = prepare(second, device=device).json()
    assert assessment["tasks"][0]["id"] == alias["id"]
    assert activate(second, assessment, device).status_code == 200
    clock[0] += timedelta(seconds=1)
    assert save(second, assessment, device, {alias["id"]: first_input}).status_code == 200
    context = _record(second, assessment)["answer_context"][alias["id"]]
    assert context["owner_ids"] == [second_owner] and context["assisted"] is False
    source_exposures = [row for row in _rows(first.app.state.database, SeenTask)["seen_tasks"]
                        if row["guest_id"] == first_owner]
    clock[0] += timedelta(seconds=1)
    owners = login(second, mailbox)["owner_ids"]
    assert set(owners) == {*account["owner_ids"], second_owner}
    final_answers = _answers(second, assessment)
    assert save(second, assessment, device, final_answers, revision=1).status_code == 200
    completed = finalize(second, assessment, device, final_answers)
    assert completed.status_code == 200, completed.text
    result = completed.json()["server_result"]
    assert result["independent_total"] == 12
    assert result["rows"][0]["assisted"] is result["rows"][0]["independent"] is False
    assert _record(second, assessment)["guest_id"] == second_owner
    assert _record(second, assessment)["answer_context"][alias["id"]] == context
    assert _record(second, source) == frozen
    assert [row for row in _rows(first.app.state.database, SeenTask)["seen_tasks"]
            if row["guest_id"] == first_owner] == source_exposures
    pending = view(second, source, device).json()
    assert pending["status"] == "awaiting_snapshot"
    assert pending["server_result"] is pending["local_result"] is None
    with second.app.state.database.transaction() as db:
        evidence = released_evidence(db, owners)
        assert len(evidence) == 13
        assert {row["assessment_id"] for row in evidence} == {assessment["id"]}
    clock[0] += timedelta(seconds=1)
    released = finalize(second, source, device, _answers(second, source), lost=True)
    assert released.status_code == 200, released.text
    server, local = released.json()["server_result"], released.json()["local_result"]
    assert server == frozen["server_result"]
    assert local["score"] == 13 and local["independent_total"] == 0
    assert local["rows"][0]["first_answer"] == server["rows"][0]["first_answer"]
    persisted = _record(second, source)
    assert persisted["tasks_snapshot"] == frozen["tasks_snapshot"]
    assert persisted["answer_context"][original.id] == frozen["answer_context"][original.id]
    assert persisted["first_drafts"][original.id] == frozen["first_drafts"][original.id]
    with second.app.state.database.transaction() as db:
        evidence = released_evidence(db, owners)
        assert len(evidence) == 26
        assert sum(row["correct"] for row in evidence) == 14
        assert sum(row["independent"] for row in evidence) == 13
        assert {row["id"] for row in evidence} == {
            row["id"] for row in [*server["rows"], *result["rows"]]
        }
        assert {row["id"] for row in evidence}.isdisjoint(row["id"] for row in local["rows"])


def test_deadline_cutoff_does_not_reserve_a_later_pending_alias_snapshot(
    guest_client, content_dir, single_slot_bank, clock,
):
    client = guest_client
    device = str(uuid4())
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    earlier = prepare(client, device=device, duration_minutes=15).json()
    early_active = activate(client, earlier, device).json()
    assert save(client, earlier, device, {
        original.id: {"answer": original.answer, "active_seconds": 1},
    }).status_code == 200
    alias = _alias(content_dir, original)
    later = prepare(client, device=device, duration_minutes=30).json()
    late_active = activate(client, later, device).json()
    assert save(client, later, device, {
        alias["id"]: {"answer": original.answer, "active_seconds": 1},
    }).status_code == 200
    clock[0] = datetime.fromisoformat(late_active["deadline_at"])
    # Freeze in reverse order through the real GET path, without releasing either.
    assert view(client, later, device).json()["server_result"] is None
    late_frozen = _record(client, later)["server_result"]
    assert late_frozen["snapshot_at"] == late_active["deadline_at"]
    assert view(client, earlier, device).json()["server_result"] is None
    early_frozen = _record(client, earlier)["server_result"]
    assert early_frozen["snapshot_at"] == early_active["deadline_at"]
    assert early_frozen["rows"][0]["assisted"] is False
    assert early_frozen["rows"][0]["independent"] is True
    assert _record(client, later)["server_result"] == late_frozen


def test_unrelated_owner_alias_history_does_not_affect_eligibility(
    client_factory, content_dir, single_slot_bank,
):
    first = client_factory()
    first.post("/api/v1/guest", json={})
    practice = start(first, slots=[1]).json()
    original = next(task for task in single_slot_bank.tasks if task.slot == 1)
    assert answer(first, practice, practice["tasks"][0], original.answer).status_code == 200
    previous = _rows(first.app.state.database, SeenTask, AttemptRecord, LearningSessionRecord)
    _alias(content_dir, original)
    second = client_factory(database_url=first.app.state.settings.database_url)
    owner = second.post("/api/v1/guest", json={}).json()["id"]
    device = str(uuid4())
    assessment = prepare(second, device=device).json()
    assert view(first, assessment, device).status_code == 404
    assert activate(second, assessment, device).status_code == 200
    result = finalize(second, assessment, device, _answers(second, assessment))
    assert result.status_code == 200, result.text
    assert result.json()["server_result"]["independent_total"] == 13
    assert result.json()["server_result"]["assisted_total"] == 0
    after = _rows(first.app.state.database, SeenTask, AttemptRecord, LearningSessionRecord)
    after["seen_tasks"] = [row for row in after["seen_tasks"] if row["guest_id"] != owner]
    assert after == previous


def test_fresh_static_condition_is_preferred_to_a_recent_alias(
    client_factory, content_dir, content, monkeypatch,
):
    selected = {}
    for task in content.tasks:
        selected.setdefault(task.slot, task)
    _write_tasks(content_dir, [task.model_dump(mode="json") for task in selected.values()])
    client = client_factory()
    client.post("/api/v1/guest", json={})
    practice = start(client, slots=[1]).json()
    assert practice["tasks"][0]["id"] == selected[1].id
    alias = _alias(content_dir, selected[1])
    fresh = next(task for task in content.tasks
                 if task.slot == 1 and instance_key(task) != instance_key(alias))
    _write_tasks(content_dir, [
        *(task.model_dump(mode="json") for task in load_content(content_dir).tasks),
        fresh.model_dump(mode="json"),
    ])

    def unexpected(*args, **kwargs):
        pytest.fail("all slots have fresh static conditions, so runtime must not run")

    monkeypatch.setattr("app.assessments.service.generate_candidates", unexpected)
    response = prepare(client)
    assert response.status_code == 200, response.text
    assert response.json()["tasks"][0]["id"] == fresh.id


@pytest.mark.parametrize("kind", ["guest", "account"])
@pytest.mark.parametrize("operation", ["get", "draft", "activate", "takeover", "finish", "replay"])
def test_access_expiring_after_assessment_lock_returns_401_without_writes(
    account_factory, account_config, clock, kind, operation,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    client.post("/api/v1/guest", json={})
    if kind == "account":
        login(client, mailbox)
    device, headers = str(uuid4()), key()
    assessment = prepare(client, device=device, duration_minutes=15).json()
    active = activate(client, assessment, device).json()
    if operation == "replay":
        assert finalize(client, assessment, device, {}, headers=headers).status_code == 200
    clock[0] = datetime.fromisoformat(active["deadline_at"]) - timedelta(seconds=1)
    database = client.app.state.database
    with database.transaction(write=True) as db:
        model = AccessSession if kind == "account" else Guest
        db.scalars(select(model)).one().expires_at = clock[0] + timedelta(seconds=1)
    models = (Guest, AccessSession, AssessmentRecord, IdempotencyRecord, SeenTask)
    before = _rows(database, *models)
    counters = client.app.state.operation_health.snapshot()["events"]
    with _advance_after_row_lock(database, clock, AssessmentRecord):
        if operation == "get":
            response = view(client, assessment, device)
        elif operation == "draft":
            response = save(client, assessment, device, {
                assessment["tasks"][0]["id"]: {"answer": "42", "active_seconds": 1},
            })
        elif operation == "activate":
            response = activate(client, assessment, device)
        elif operation == "takeover":
            response = takeover(client, assessment, str(uuid4()))
        else:
            response = finalize(client, assessment, device, {}, headers=headers)
    assert response.status_code == 401, response.text
    assert _rows(database, *models) == before
    assert client.app.state.operation_health.snapshot()["events"] == counters


def test_prepare_reauthorizes_after_catalog_lock_and_rolls_back_expired_access(
    guest_client, clock,
):
    database = guest_client.app.state.database
    with database.transaction(write=True) as db:
        db.scalars(select(Guest)).one().expires_at = clock[0] + timedelta(seconds=1)
    models = (Guest, EditorCatalog, AssessmentRecord, IdempotencyRecord, SeenTask)
    before = _rows(database, *models)
    with _advance_after_row_lock(database, clock, EditorCatalog):
        response = prepare(guest_client)
    assert response.status_code == 401, response.text
    assert _rows(database, *models) == before


def test_draft_counters_count_only_accepted_committed_mutations(guest_client):
    client = guest_client
    device, headers = str(uuid4()), key()
    assessment = prepare(client, device=device).json()
    assert save(client, assessment, device, {}).status_code == 409
    activated = activate(client, assessment, device, headers=headers)
    assert activated.status_code == 200
    assert activate(client, assessment, device, headers=headers).content == activated.content
    task_id = assessment["tasks"][0]["id"]
    assert save(client, assessment, str(uuid4()), {}).status_code == 409
    assert save(client, assessment, device, {
        "foreign-task": {"answer": "12", "active_seconds": 0},
    }).status_code == 422
    assert save(client, assessment, device, {}, revision=1).status_code == 409
    assert save(client, assessment, device, {
        task_id: {"answer": 12, "active_seconds": 0},
    }).status_code == 422
    health = client.app.state.operation_health
    assert health.snapshot()["events"]["draft_save"] == {"successes": 0, "failures": 0}
    assert save(client, assessment, device, {
        task_id: {"answer": "NaN", "active_seconds": 2},
    }).status_code == 200
    assert save(client, assessment, device, {}).status_code == 409
    assert view(client, assessment, device).status_code == 200
    assert health.snapshot()["events"]["draft_save"] == {"successes": 1, "failures": 0}
    assert health.snapshot()["events"]["answer_check"] == {"successes": 0, "failures": 0}


def test_failed_draft_commit_counts_failure_and_preserves_all_input_history(
    guest_client, monkeypatch,
):
    client = guest_client
    device = str(uuid4())
    assessment = prepare(client, device=device).json()
    assert activate(client, assessment, device).status_code == 200
    database = client.app.state.database
    original = database.transaction
    before = _record(client, assessment)
    health = client.app.state.operation_health

    @contextmanager
    def failing_commit(*, write=False):
        with original(write=write) as db:
            yield db
            if write:
                assert health.snapshot()["events"]["draft_save"] == {
                    "successes": 0, "failures": 0,
                }
                raise OperationalError("synthetic assessment commit failure", None, None)

    with monkeypatch.context() as patch:
        patch.setattr(database, "transaction", failing_commit)
        response = save(client, assessment, device, {
            assessment["tasks"][0]["id"]: {"answer": "12", "active_seconds": 2},
        })
    assert response.status_code == 503, response.text
    assert health.snapshot()["events"]["draft_save"] == {"successes": 0, "failures": 1}
    assert _record(client, assessment) == before


@pytest.mark.parametrize("completion", ["online", "connection-lost", "deadline"])
def test_answer_checks_are_counted_at_server_and_local_grading_not_drafts_or_replays(
    guest_client, clock, completion,
):
    client = guest_client
    device, headers = str(uuid4()), key()
    assessment = prepare(client, device=device, duration_minutes=15).json()
    active = activate(client, assessment, device).json()
    tasks = assessment["tasks"]
    answers = {
        tasks[0]["id"]: _answers(client, assessment)[tasks[0]["id"]],
        tasks[1]["id"]: {"answer": "999999", "active_seconds": 2},
        tasks[2]["id"]: {"answer": "NaN", "active_seconds": 3},
    }
    assert save(client, assessment, device, answers).status_code == 200
    health = client.app.state.operation_health
    assert health.snapshot()["events"]["answer_check"] == {"successes": 0, "failures": 0}
    if completion == "deadline":
        clock[0] = datetime.fromisoformat(active["deadline_at"])
        assert client.app.state.assessments.reconcile_deadlines() == 1
        assert health.snapshot()["events"]["answer_check"] == {"successes": 2, "failures": 1}
        assert view(client, assessment, device).json()["server_result"] is None
        assert client.app.state.assessments.reconcile_deadlines() == 0
    lost = completion != "online"
    finished = finalize(client, assessment, device, answers, lost=lost, headers=headers)
    assert finished.status_code == 200, finished.text
    expected = {"successes": 4, "failures": 2} if lost else {"successes": 2, "failures": 1}
    assert health.snapshot()["events"]["answer_check"] == expected
    assert finalize(
        client, assessment, device, answers, lost=lost, headers=headers,
    ).content == finished.content
    assert finalize(client, assessment, device, answers, lost=lost).status_code == 200
    assert view(client, assessment, device).status_code == 200
    assert health.snapshot()["events"]["answer_check"] == expected
