from datetime import timedelta
from uuid import uuid4

from sqlalchemy import select

from app.models import AttemptRecord, Guest, IdempotencyRecord
from tests.helpers import answer, expected, start
from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory
from tests.test_concurrency import race


def test_claim_preserves_core_access_origins_and_exact_replay(account_factory, account_config):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    origin = client.post("/api/v1/guest", json={}).json()["id"]
    legacy_cookie = client.cookies.get("math_ege_guest")
    headers = {"Idempotency-Key": str(uuid4())}
    created = start(client, headers=headers)
    account = login(client, mailbox)
    identity = client.get("/api/v1/identity")
    assert identity.status_code == 200, identity.text
    assert identity.json() == {
        "id": account["root_guest_id"], "kind": "account", "owner_ids": account["owner_ids"],
    }
    assert start(client, headers=headers).content == created.content
    session = created.json()
    assert client.get(f"/api/v1/sessions/{session['id']}").json() == session
    response = answer(client, session, session["tasks"][0], "42")
    assert response.status_code == 200, response.text
    with client.app.state.database.transaction() as db:
        attempt = db.get(AttemptRecord, response.json()["id"])
        assert attempt.guest_id == origin
        replay = db.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.request_key == headers["Idempotency-Key"],
        ))
        assert replay.guest_id == origin
    assert len(client.get("/api/v1/export").json()["sessions"]) == 1
    stale = account_factory(database_url=client.app.state.settings.database_url)
    stale.cookies.set("math_ege_guest", legacy_cookie)
    assert stale.get(f"/api/v1/sessions/{session['id']}").status_code == 401


def test_guest_endpoint_preserves_account_cookie_and_access_lifetime(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    account = login(client, mailbox)
    cookie = client.cookies.get("math_ege_guest")
    with client.app.state.database.transaction(write=True) as db:
        db.get(Guest, account["root_guest_id"]).expires_at = clock[0] - timedelta(days=1)
    response = client.post("/api/v1/guest", json={})
    assert response.json()["id"] == account["root_guest_id"]
    assert client.cookies.get("math_ege_guest") == cookie
    assert "Max-Age=2592000" in response.headers["set-cookie"]
    assert start(client).status_code == 200


def test_merged_exposure_and_independence_span_all_origins(
    account_factory, account_config, content,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    first.post("/api/v1/guest", json={})
    session = start(first).json()
    task = session["tasks"][0]
    account = login(first, mailbox)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    second.post("/api/v1/guest", json={})
    other = start(second).json()
    same = next(item for item in other["tasks"] if item["id"] == task["id"])
    assert second.post(
        f"/api/v1/sessions/{other['id']}/hints", json={"task_id": same["id"], "level": 1},
    ).status_code == 200
    assert login(second, mailbox)["id"] == account["id"]
    responses = race(*(
        lambda client=client, saved=saved: answer(client, saved, task, expected(content, task))
        for client, saved in ((first, session), (second, other))
    ))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["assisted"] for response in responses)
    assert not any(response.json()["independent"] for response in responses)
    assert start(first).status_code == 409
    assert len(first.get("/api/v1/export").json()["sessions"]) == 2


def test_merged_changed_body_key_conflicts_without_a_new_session(account_factory, account_config):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    client.post("/api/v1/guest", json={})
    headers = {"Idempotency-Key": str(uuid4())}
    assert start(client, headers=headers).status_code == 200
    login(client, mailbox)
    response = client.post(
        "/api/v1/sessions", json={"slots": [2], "length": 5, "mode": "practice"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"
    assert len(client.get("/api/v1/export").json()["sessions"]) == 1


def test_extended_claimed_session_keeps_exposure_with_its_historical_owner(
    account_factory, account_config,
):
    from app.models import SeenTask

    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    origin = client.post("/api/v1/guest", json={}).json()["id"]
    response = client.post("/api/v1/sessions", json={
        "slots": [1, 2], "length": 5, "mode": "practice", "until_stopped": True,
    }, headers={"Idempotency-Key": str(uuid4())})
    assert response.status_code == 200, response.text
    initial = response.json()
    for task in initial["tasks"]:
        assert answer(client, initial, task, "", skipped=True).status_code == 200
    login(client, mailbox)
    response = client.post(f"/api/v1/sessions/{initial['id']}/extend", json={}, headers={
        "Idempotency-Key": str(uuid4()),
    })
    assert response.status_code == 200, response.text
    extended = response.json()
    task = extended["tasks"][len(initial["tasks"])]
    help_response = client.post(f"/api/v1/sessions/{initial['id']}/hints", json={
        "task_id": task["id"], "level": 1,
    })
    assert help_response.status_code == 200, help_response.text
    result = answer(client, extended, task, "42")
    assert result.status_code == 200, result.text
    assert result.json()["assisted"]
    with client.app.state.database.transaction() as db:
        seen = db.scalar(select(SeenTask).where(SeenTask.task_id == task["id"]))
        assert seen.guest_id == origin and seen.assistance_seen
        assert db.get(AttemptRecord, result.json()["id"]).guest_id == origin
