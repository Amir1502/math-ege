import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app import generators
from app.config import DEFAULT_CONTENT_DIR, Settings
from app.content import load_content
from app.editor.models import EditorPublication
from app.instances import instance_key
from app.models import Guest, IdempotencyRecord, LearningSessionRecord, SeenTask
from tests.helpers import answer

FAMILY = "right-triangle-area"
COURSE = Path(__file__).resolve().parents[1] / "content" / "course"


@pytest.fixture
def generated_dir(content_dir, content):
    anchor = generators.generate(FAMILY, 0, content.profile)
    tasks = [task.model_dump(mode="json") for task in content.tasks if task.slot != 1]
    (content_dir / "tasks.json").write_text(
        json.dumps([anchor.model_dump(mode="json"), *tasks], ensure_ascii=False), encoding="utf-8",
    )
    return content_dir


def start_generated(client, headers=None, **options):
    return client.post(
        "/api/v1/sessions", headers=headers or {"Idempotency-Key": str(uuid4())},
        json={"slots": [1], "length": 5, "mode": "practice", "family_ids": [FAMILY], **options},
    )


def test_expanded_course_is_the_default_without_replacing_legacy_files(client_factory):
    assert DEFAULT_CONTENT_DIR == COURSE
    assert Settings().content_dir == COURSE
    client = client_factory(content_dir=Settings().content_dir)
    assert client.get("/api/v1/profile").json()["bank_size"] == 845
    curriculum = client.get("/api/v1/curriculum").json()
    assert len(curriculum["lessons"]) == 99
    assert len(load_content(COURSE.parent).tasks) == 65


@pytest.mark.parametrize("selection", ["balanced", "mixed"])
def test_runtime_fills_a_static_shortage_with_unique_frozen_conditions(
    client_factory, generated_dir, selection,
):
    client = client_factory(content_dir=generated_dir)
    assert client.post("/api/v1/guest", json={}).status_code == 200
    response = start_generated(client, selection=selection)
    assert response.status_code == 200, response.text
    session = response.json()
    assert len(session["tasks"]) == 5
    assert {task["family_id"] for task in session["tasks"]} == {FAMILY}
    assert len({instance_key(task) for task in session["tasks"]}) == 5
    assert all(not {"generation", "answer", "hints", "solution", "source", "instance_key"}
               & task.keys() for task in session["tasks"])
    with client.app.state.database.transaction() as db:
        record = db.get(LearningSessionRecord, session["id"])
        assert len(record.tasks_snapshot) == 5
        assert all(task["generation"]["template_id"] == FAMILY for task in record.tasks_snapshot)
        assert all(task["generation"]["template_version"] == "1"
                   for task in record.tasks_snapshot)
        exposures = list(db.scalars(select(SeenTask)))
        assert {item.task_id for item in exposures} == {task["id"] for task in session["tasks"]}
        assert {item.instance_key for item in exposures} == {
            instance_key(task) for task in record.tasks_snapshot
        }


def test_runtime_replay_survives_withdrawal_without_a_new_generation(
    client_factory, generated_dir, clock, monkeypatch,
):
    client = client_factory(content_dir=generated_dir)
    client.post("/api/v1/guest", json={})
    headers = {"Idempotency-Key": str(uuid4()).upper()}
    first = start_generated(client, headers)
    assert first.status_code == 200 and len(first.json()["tasks"]) == 5
    with client.app.state.database.transaction(write=True) as db:
        db.add(EditorPublication(
            kind="template", content_id=FAMILY, revision_id=None, withdrawn=True,
            reason="Synthetic withdrawal fixture", updated_at=clock[0],
        ))
    with monkeypatch.context() as patch:
        def unexpected_generation(*args, **kwargs):
            pytest.fail("a durable replay must not call a generator")

        patch.setattr(generators, "generate", unexpected_generation)
        replay = start_generated(client, {"Idempotency-Key": headers["Idempotency-Key"].lower()})
    assert replay.content == first.content
    assert start_generated(client).status_code == 409
    assert client.get(f"/api/v1/sessions/{first.json()['id']}").json()["tasks"] == first.json()[
        "tasks"
    ]


def test_continuation_excludes_every_earlier_snapshot_even_after_thirty_days(
    client_factory, generated_dir, clock,
):
    client = client_factory(content_dir=generated_dir)
    client.post("/api/v1/guest", json={})
    first = start_generated(client, until_stopped=True).json()
    assert len(first["tasks"]) == 5
    for task in first["tasks"]:
        assert answer(client, first, task, "", skipped=True).status_code == 200
    clock[0] += timedelta(days=31)
    headers = {"Idempotency-Key": str(uuid4())}
    extended = client.post(f"/api/v1/sessions/{first['id']}/extend", json={}, headers=headers)
    assert extended.status_code == 200, extended.text
    assert extended.json()["tasks"][:5] == first["tasks"]
    assert len(extended.json()["tasks"]) == 10
    assert len({instance_key(task) for task in extended.json()["tasks"]}) == 10
    assert client.post(
        f"/api/v1/sessions/{first['id']}/extend", json={}, headers=headers,
    ).content == extended.content


def test_static_aliases_are_not_issued_as_distinct_new_instances(client_factory, content_dir):
    tasks = json.loads((content_dir / "tasks.json").read_text(encoding="utf-8"))
    one = next(task for task in tasks if task["slot"] == 1)
    alias = {**one, "id": "synthetic-visible-alias"}
    tasks = [task for task in tasks if task["slot"] != 1] + [one, alias]
    (content_dir / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False), encoding="utf-8")
    client = client_factory()
    client.post("/api/v1/guest", json={})
    body = {"slots": [1], "length": 5, "mode": "practice"}
    first = client.post("/api/v1/sessions", json=body, headers={"Idempotency-Key": str(uuid4())})
    assert first.status_code == 200
    assert len(first.json()["tasks"]) == 1
    assert client.post(
        "/api/v1/sessions", json=body, headers={"Idempotency-Key": str(uuid4())},
    ).status_code == 409


def test_catalog_waiting_rechecks_guest_expiry_without_persisting_a_rejected_request(
    guest_client, clock, monkeypatch,
):
    from app import services
    from app.editor.repository import lock_catalog

    database = guest_client.app.state.database
    with database.transaction(write=True) as db:
        db.scalars(select(Guest)).one().expires_at = clock[0] + timedelta(seconds=1)

    def delayed_lock(db):
        catalog = lock_catalog(db)
        clock[0] += timedelta(seconds=2)
        return catalog

    monkeypatch.setattr(services, "lock_catalog", delayed_lock, raising=False)
    result = guest_client.post(
        "/api/v1/sessions", json={"slots": [1], "length": 5, "mode": "practice"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert result.status_code == 401, result.text
    with database.transaction() as db:
        for model in (LearningSessionRecord, SeenTask, IdempotencyRecord):
            assert db.scalar(select(func.count()).select_from(model)) == 0
