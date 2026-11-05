import json
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import generators
from app.assessments.models import AssessmentRecord
from app.editor.models import CorrectionExclusion, EditorPublication
from app.instances import instance_key
from app.models import AttemptRecord, LearningSessionRecord, SeenTask
from tests.helpers import answer
from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory
from tests.test_assessments import activate, finalize, prepare
from tests.test_runtime_integration import FAMILY, start_generated
from tests.test_runtime_integration import generated_dir as generated_dir


def runtime_history(client):
    client.post("/api/v1/guest", json={})
    response = start_generated(client)
    assert response.status_code == 200, response.text
    session = response.json()
    with client.app.state.database.transaction() as db:
        record = db.get(LearningSessionRecord, session["id"])
        frozen = deepcopy(record.tasks_snapshot)
    task = next(task for task in frozen if task["generation"]["seed"] != 0)
    return session, task, frozen


def test_owned_runtime_repeat_preserves_snapshots_provenance_and_independent_credit(
    client_factory, generated_dir,
):
    client = client_factory(content_dir=generated_dir)
    original, task, frozen = runtime_history(client)
    first = answer(client, original, task, task["answer"])
    assert first.status_code == 200 and first.json()["independent"]
    original_view = client.get(f"/api/v1/sessions/{original['id']}").json()
    counters = client.app.state.service.operation_health.snapshot()["events"]["generator"]
    headers = {"Idempotency-Key": str(uuid4())}

    repeated = start_generated(client, headers, repeat_task_id=task["id"])

    assert repeated.status_code == 200, repeated.text
    assert [item["id"] for item in repeated.json()["tasks"]] == [task["id"]]
    assert "повтор" in repeated.json()["notice"].lower()
    assert not {"generation", "answer", "hints", "solution", "source", "instance_key"} & (
        repeated.json()["tasks"][0].keys()
    )
    after = client.app.state.service.operation_health.snapshot()["events"]["generator"]
    assert after["successes"] == counters["successes"] + 1
    assert after["failures"] == counters["failures"]
    assert start_generated(client, headers, repeat_task_id=task["id"]).content == repeated.content
    assert client.app.state.service.operation_health.snapshot()["events"]["generator"] == after
    submitted = answer(client, repeated.json(), task, task["answer"])
    assert submitted.status_code == 200
    assert submitted.json()["correct"] and not submitted.json()["independent"]
    assert client.get(f"/api/v1/sessions/{original['id']}").json() == original_view
    with client.app.state.database.transaction() as db:
        assert db.get(LearningSessionRecord, original["id"]).tasks_snapshot == frozen
        assert db.get(LearningSessionRecord, repeated.json()["id"]).tasks_snapshot == [task]
        assert db.get(AttemptRecord, first.json()["id"]).independent


def test_claimed_origin_runtime_repeat_writes_only_the_new_canonical_session_scope(
    account_factory, account_config, generated_dir,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox, content_dir=generated_dir)
    original, task, frozen = runtime_history(client)
    initial = answer(client, original, task, task["answer"]).json()
    with client.app.state.database.transaction() as db:
        origin = db.get(LearningSessionRecord, original["id"]).guest_id
        seen_before = deepcopy(db.scalars(select(SeenTask).where(
            SeenTask.guest_id == origin, SeenTask.task_id == task["id"],
        )).one().instance_key)
    account = login(client, mailbox)
    assert account["root_guest_id"] != origin

    repeated = start_generated(client, repeat_task_id=task["id"])

    assert repeated.status_code == 200, repeated.text
    submitted = answer(client, repeated.json(), task, task["answer"]).json()
    assert not submitted["independent"]
    with client.app.state.database.transaction() as db:
        assert db.get(LearningSessionRecord, original["id"]).guest_id == origin
        assert db.get(LearningSessionRecord, original["id"]).tasks_snapshot == frozen
        assert db.get(AttemptRecord, initial["id"]).guest_id == origin
        assert db.get(AttemptRecord, submitted["id"]).guest_id == account["root_guest_id"]
        records = list(db.scalars(select(SeenTask).where(SeenTask.task_id == task["id"])))
        assert {row.guest_id for row in records} == {origin, account["root_guest_id"]}
        assert {row.instance_key for row in records} == {seen_before, instance_key(task)}


@pytest.mark.parametrize("gate", ["template", "task", "correction", "demo", "filter"])
def test_runtime_repeat_denials_do_not_regenerate_or_change_history(
    client_factory, generated_dir, clock, monkeypatch, gate,
):
    client = client_factory(content_dir=generated_dir)
    original, task, frozen = runtime_history(client)
    service = client.app.state.service
    if gate == "demo":
        service.settings = replace(service.settings, allow_demo_content=False)
    elif gate != "filter":
        with client.app.state.database.transaction(write=True) as db:
            if gate == "correction":
                db.add(CorrectionExclusion(
                    id=str(uuid4()), task_id=task["id"], task_revision=task["revision"],
                    reason="Synthetic correction", actor_id="synthetic-editor", created_at=clock[0],
                ))
            else:
                db.add(EditorPublication(
                    kind=gate, content_id=FAMILY if gate == "template" else task["id"],
                    revision_id=None, withdrawn=True, reason="Synthetic withdrawal",
                    updated_at=clock[0],
                ))
    counters = service.operation_health.snapshot()["events"]["generator"]

    def unexpected_generation(*args, **kwargs):
        pytest.fail("a denied repeat must not invoke a generator")

    monkeypatch.setattr(generators, "generate", unexpected_generation)
    response = start_generated(
        client, repeat_task_id=task["id"],
        **({"difficulty": 3 if task["difficulty"] != 3 else 1} if gate == "filter" else {}),
    )

    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "task_unavailable"
    assert service.operation_health.snapshot()["events"]["generator"] == counters
    with client.app.state.database.transaction() as db:
        assert db.get(LearningSessionRecord, original["id"]).tasks_snapshot == frozen
        assert len(list(db.scalars(select(LearningSessionRecord)))) == 1


def test_foreign_runtime_snapshot_cannot_be_repeated_or_used_as_source_authority(
    client_factory, generated_dir, monkeypatch,
):
    owner = client_factory(content_dir=generated_dir)
    original, task, frozen = runtime_history(owner)
    foreign = client_factory(
        content_dir=generated_dir, database_url=owner.app.state.settings.database_url,
    )
    foreign.post("/api/v1/guest", json={})

    def unexpected_generation(*args, **kwargs):
        pytest.fail("a foreign snapshot must not reach reconstruction")

    monkeypatch.setattr(generators, "generate", unexpected_generation)
    response = start_generated(foreign, repeat_task_id=task["id"])

    assert response.status_code == 404, response.text
    assert foreign.get(f"/api/v1/sessions/{original['id']}").status_code == 404
    assert foreign.app.state.service.operation_health.snapshot()["events"]["generator"][
        "successes"
    ] == 0
    with owner.app.state.database.transaction() as db:
        assert db.get(LearningSessionRecord, original["id"]).tasks_snapshot == frozen
        assert len(list(db.scalars(select(LearningSessionRecord)))) == 1


@pytest.mark.parametrize("stage", ["prepared", "active", "awaiting_snapshot", "completed"])
def test_assessment_runtime_repeat_requires_released_canonical_server_history(
    client_factory, generated_dir, content, clock, stage,
):
    client = client_factory(content_dir=generated_dir)
    client.post("/api/v1/guest", json={})
    device = str(uuid4())
    prepared = prepare(client, device=device, duration_minutes=15)
    assert prepared.status_code == 200, prepared.text
    assessment = prepared.json()
    task = next(task for task in assessment["tasks"] if task["slot"] == 1)
    if stage != "prepared":
        assert activate(client, assessment, device).status_code == 200
    if stage == "awaiting_snapshot":
        clock[0] += timedelta(minutes=16)
        client.app.state.assessments.reconcile_deadlines()
    elif stage == "completed":
        finished = finalize(client, assessment, device, {})
        assert finished.status_code == 200, finished.text
    with client.app.state.database.transaction() as db:
        record = db.get(AssessmentRecord, assessment["id"])
        frozen = deepcopy(record.tasks_snapshot)
        result = deepcopy(record.server_result)
        assert record.status == stage
    replacement = generators.generate(FAMILY, 1, content.profile).model_dump(mode="json")
    path = generated_dir / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps([
        replacement if item["id"] == task["id"] else item for item in tasks
    ], ensure_ascii=False), encoding="utf-8")
    counters = client.app.state.service.operation_health.snapshot()["events"]["generator"]

    repeated = start_generated(client, repeat_task_id=task["id"])

    assert repeated.status_code == (200 if stage == "completed" else 404), repeated.text
    after = client.app.state.service.operation_health.snapshot()["events"]["generator"]
    assert after["successes"] == counters["successes"] + (stage == "completed")
    assert after["failures"] == counters["failures"]
    with client.app.state.database.transaction() as db:
        record = db.get(AssessmentRecord, assessment["id"])
        assert record.tasks_snapshot == frozen and record.server_result == result
        assert record.local_result is None
        if stage == "completed":
            assert db.get(LearningSessionRecord, repeated.json()["id"]).tasks_snapshot == [
                next(item for item in frozen if item["id"] == task["id"])
            ]
        else:
            assert not list(db.scalars(select(LearningSessionRecord)))
            exported = client.get("/api/v1/export").json()["assessments"][0]
            assert exported["server_result"] is None and exported["local_result"] is None
