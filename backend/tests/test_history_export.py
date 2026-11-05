from datetime import timedelta
from uuid import uuid4

from tests.helpers import answer, expected, key, start
from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory


def test_complete_export_keeps_all_annotations_and_original_practice_profiles(guest_client):
    created = []
    for _ in range(3):
        response = start(guest_client, slots=list(range(1, 14)), length=20)
        assert response.status_code == 200, response.text
        session = response.json()
        created.append(session)
        for task in session["tasks"]:
            response = guest_client.post("/api/v1/learning/annotations", json={
                "session_id": session["id"], "task_id": task["id"], "favourite": True,
            }, headers=key())
            assert response.status_code == 200, response.text
    response = guest_client.get("/api/v1/export")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["learning"]["annotations"]) == 60
    assert {item["id"] for item in data["sessions"]} == {item["id"] for item in created}
    assert all(item["profile"]["revision"] == item["profile_revision"]
               for item in data["sessions"])
    assert data["account"] is None and data["assessments"] == []
    assert data["learning"]["algorithm_version"] == "learning-v1"


def test_export_preserves_separate_results_and_never_releases_pending_snapshot(
    guest_client, content, clock,
):
    device = str(uuid4())
    prepared = guest_client.post("/api/v1/assessments", json={
        "mode": "exam", "duration_minutes": 15, "device_id": device,
    }, headers=key()).json()
    path = f"/api/v1/assessments/{prepared['id']}"
    writer = {"device_id": device, "writer_generation": 1}
    assert guest_client.post(f"{path}/activate", json=writer, headers=key()).status_code == 200
    clock[0] += timedelta(minutes=16)
    guest_client.app.state.assessments.reconcile_deadlines()
    pending = guest_client.get("/api/v1/export").json()["assessments"][0]
    assert pending["status"] == "awaiting_snapshot"
    assert pending["server_result"] is pending["local_result"] is None
    assert all("answer" not in task and "solution" not in task for task in pending["tasks"])
    assert "writer_device_id" not in pending and "writer_generation" not in pending
    task = prepared["tasks"][0]
    response = guest_client.post(f"{path}/finish", json={
        **writer, "connection_lost": True,
        "answers": {task["id"]: {"answer": expected(content, task), "active_seconds": 12}},
    }, headers=key())
    assert response.status_code == 200, response.text
    data = guest_client.get("/api/v1/export").json()
    result = data["assessments"][0]
    assert result["server_result"] == response.json()["server_result"]
    assert result["local_result"] == response.json()["local_result"]
    assert result["server_result"]["score"] == 0 and result["local_result"]["score"] == 1
    assert len(data["learning"]["reviews"]) >= 13


def test_account_export_combines_claimed_history_without_authentication_secrets(
    account_factory, account_config, content,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    first.post("/api/v1/guest", json={})
    session = start(first).json()
    task = session["tasks"][0]
    submitted = answer(first, session, task, expected(content, task)).json()
    account = login(first, mailbox)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    second.post("/api/v1/guest", json={})
    other = start(second, slots=[2]).json()
    login(second, mailbox)
    response = second.get("/api/v1/export")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["account"]["id"] == account["id"]
    assert data["account"]["email"] == account["email"]
    assert data["account"]["consents"]
    assert {item["id"] for item in data["sessions"]} == {session["id"], other["id"]}
    exported_attempts = [
        attempt["id"] for item in data["sessions"] for attempt in item["attempts"]
    ]
    assert exported_attempts == [submitted["id"]]
    forbidden = {"token_digest", "browser_state_digest", "secret_ciphertext", "last_timecode",
                 "writer_device_id", "mfa_verified_at", "access_sessions", "account_magic_links"}

    def keys(value):
        if isinstance(value, dict):
            return set(value) | set().union(*(keys(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(item) for item in value))
        return set()

    assert not keys(data) & forbidden
    assert second.cookies.get("math_ege_guest") not in response.text
