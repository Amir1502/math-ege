import json
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.editor.models import CorrectionExclusion
from app.models import LearningSessionRecord
from tests.helpers import answer, expected, key, start


def test_learning_and_editor_routes_are_available_and_documented(guest_client):
    paths = guest_client.app.openapi()["paths"]
    assert "/api/v1/learning/dashboard" in paths
    assert "/api/v1/editor/meta" in paths
    response = guest_client.get("/api/v1/learning/dashboard")
    assert response.status_code == 200, response.text
    assert response.json()["independent_total"] == 0
    assert guest_client.get("/api/v1/editor/meta").status_code == 503


def test_help_opens_review_immediately_without_inventing_an_attempt(guest_client, clock):
    session = start(guest_client).json()
    task = session["tasks"][0]
    endpoint = f"/api/v1/sessions/{session['id']}/hints"
    body = {"task_id": task["id"], "level": 1}
    assert guest_client.post(endpoint, json=body).status_code == 200
    dashboard = guest_client.get("/api/v1/learning/dashboard").json()
    due_at = (clock[0] + timedelta(days=1)).isoformat()
    assert dashboard["reviews"]
    assert {review["due_at"] for review in dashboard["reviews"]} == {due_at}
    assert dashboard["independent_total"] == 0
    clock[0] += timedelta(hours=2)
    assert guest_client.post(endpoint, json=body).status_code == 200
    assert {review["due_at"] for review in guest_client.get(
        "/api/v1/learning/dashboard",
    ).json()["reviews"]} == {due_at}
    saved = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    assert saved["attempts"] == []


def test_core_progress_excludes_erroneous_revision_but_keeps_historical_result(
    guest_client, content, clock,
):
    session = start(guest_client).json()
    task = session["tasks"][0]
    assert answer(guest_client, session, task, expected(content, task)).status_code == 200
    before = guest_client.get(f"/api/v1/sessions/{session['id']}").json()
    with guest_client.app.state.database.transaction(write=True) as db:
        db.add(CorrectionExclusion(
            id=str(uuid4()), task_id=task["id"], task_revision=task["revision"],
            reason="Неверное условие", created_at=clock[0], actor_id="review-fixture",
        ))
    progress = guest_client.get("/api/v1/progress")
    assert progress.status_code == 200, progress.text
    assert progress.json()["independent_total"] == 0
    assert progress.json()["excluded_total"] == 1
    assert progress.json()["notice"]
    assert guest_client.get(f"/api/v1/sessions/{session['id']}").json() == before


def test_core_progress_joins_legacy_snapshots_by_stable_slot_id(
    guest_client, content, content_dir,
):
    session = start(guest_client).json()
    task = session["tasks"][0]
    assert answer(guest_client, session, task, expected(content, task)).status_code == 200
    profile = json.loads((content_dir / "profile.json").read_text(encoding="utf-8"))
    for slot in profile["slots"]:
        if slot["number"] in {1, 2}:
            slot["number"] = 3 - slot["number"]
    profile["revision"] = "renumbered-test"
    for name in ("tasks.json", "lessons.json"):
        rows = json.loads((content_dir / name).read_text(encoding="utf-8"))
        for row in rows:
            old = row["slot"]
            row["slot_id"] = next(slot.id for slot in content.profile.slots if slot.number == old)
            if old in {1, 2}:
                row["slot"] = 3 - old
        (content_dir / name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (content_dir / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False), encoding="utf-8",
    )
    result = guest_client.get("/api/v1/progress")
    assert result.status_code == 200, result.text
    slots = {slot["number"]: slot for slot in result.json()["slots"]}
    assert slots[1]["attempts"] == 0 and slots[2]["attempts"] == 1
    with guest_client.app.state.database.transaction() as db:
        saved = db.scalar(select(LearningSessionRecord).where(
            LearningSessionRecord.id == session["id"],
        ))
        assert saved.tasks_snapshot[0]["slot"] == 1
        assert saved.profile_revision == content.profile.revision


def test_mixed_start_uses_disjoint_policy_selection_and_preserves_notice(guest_client):
    response = guest_client.post("/api/v1/sessions", json={
        "slots": [1, 2], "length": 10, "mode": "practice", "selection": "mixed",
    }, headers=key())
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["tasks"]) == 10
    assert len({task["id"] for task in result["tasks"]}) == 10
    assert "новые семейства — 10" in result["notice"]


def test_core_progress_uses_only_released_canonical_assessment_evidence(guest_client, content):
    device = str(uuid4())
    prepared = guest_client.post("/api/v1/assessments", json={
        "mode": "diagnostic", "device_id": device,
    }, headers=key()).json()
    endpoint = f"/api/v1/assessments/{prepared['id']}"
    writer = {"device_id": device, "writer_generation": 1}
    assert guest_client.post(f"{endpoint}/activate", json=writer, headers=key()).status_code == 200
    assert guest_client.get("/api/v1/progress").json()["independent_total"] == 0
    task = prepared["tasks"][0]
    response = guest_client.post(f"{endpoint}/finish", json={
        **writer, "connection_lost": False,
        "answers": {task["id"]: {"answer": expected(content, task), "active_seconds": 12}},
    }, headers=key())
    assert response.status_code == 200, response.text
    progress = guest_client.get("/api/v1/progress").json()
    assert progress["independent_total"] == progress["independent_correct"] == 1
    assert progress["skipped_total"] == 12
    assert progress["slots"][0]["status"] == "Изучаю"
