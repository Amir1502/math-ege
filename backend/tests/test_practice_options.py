import hashlib
import json
from uuid import uuid4

from sqlalchemy import select

from app.models import IdempotencyRecord


def start(client, **options):
    return client.post(
        "/api/v1/sessions", headers={"Idempotency-Key": str(uuid4())},
        json={"slots": [6], "length": 5, "mode": "practice", **options},
    )


def test_family_and_difficulty_filters_do_not_silently_substitute_other_types(
    guest_client, content,
):
    task = next(task for task in content.tasks if task.slot == 6)
    response = start(guest_client, family_ids=[task.family_id], difficulty=task.difficulty)
    assert response.status_code == 200
    assert {item["family_id"] for item in response.json()["tasks"]} == {task.family_id}
    assert response.json()["options"]["family_ids"] == [task.family_id]


def test_unknown_skill_is_rejected_instead_of_ignored(guest_client):
    assert start(guest_client, skill_ids=["unknown-skill"]).status_code == 422


def test_explicit_repeat_is_labelled_and_never_creates_second_independent_evidence(
    guest_client, content,
):
    first = start(guest_client).json()
    task = first["tasks"][0]
    answer = next(item.answer for item in content.tasks if item.id == task["id"])
    body = {"task_id": task["id"], "answer": answer, "active_seconds": 1, "skipped": False}
    initial = guest_client.post(
        f"/api/v1/sessions/{first['id']}/attempts", json=body,
        headers={"Idempotency-Key": str(uuid4())},
    ).json()
    assert initial["independent"] is True
    repeated = start(guest_client, repeat_task_id=task["id"]).json()
    assert [item["id"] for item in repeated["tasks"]] == [task["id"]]
    assert "повтор" in repeated["notice"].lower()
    result = guest_client.post(
        f"/api/v1/sessions/{repeated['id']}/attempts", json=body,
        headers={"Idempotency-Key": str(uuid4())},
    ).json()
    assert result["independent"] is False


def test_until_stopped_appends_new_conditions_without_changing_previous_snapshots(guest_client):
    first = start(guest_client, slots=[1, 2, 3], until_stopped=True, target_minutes=10).json()
    for task in first["tasks"]:
        response = guest_client.post(
            f"/api/v1/sessions/{first['id']}/attempts",
            json={"task_id": task["id"], "answer": "", "active_seconds": 1, "skipped": True},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 200
    key = {"Idempotency-Key": str(uuid4())}
    result = guest_client.post(f"/api/v1/sessions/{first['id']}/extend", json={}, headers=key)
    assert result.status_code == 200
    assert result.json()["tasks"][:5] == first["tasks"]
    assert len(result.json()["tasks"]) == 10
    assert len({task["id"] for task in result.json()["tasks"]}) == 10
    replay = guest_client.post(f"/api/v1/sessions/{first['id']}/extend", json={}, headers=key)
    assert replay.content == result.content
    assert result.json()["options"]["target_minutes"] == 10


def test_new_optional_fields_do_not_change_legacy_request_hash(guest_client):
    body = {"slots": [1], "length": 5, "mode": "practice"}
    key = str(uuid4())
    assert guest_client.post(
        "/api/v1/sessions", json=body, headers={"Idempotency-Key": key},
    ).status_code == 200
    canonical = json.dumps(
        {"operation": "POST /sessions", "body": body}, ensure_ascii=False,
        allow_nan=False, sort_keys=True, separators=(",", ":"),
    )
    with guest_client.app.state.database.transaction() as db:
        record = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.request_key == key))
        assert record.request_hash == hashlib.sha256(canonical.encode()).hexdigest()
