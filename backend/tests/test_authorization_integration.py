from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.accounts.models import AccessSession, Account
from app.editor.models import EditorAudit, EditorPublication, EditorRevision
from app.models import Guest, IdempotencyRecord, LearningSessionRecord
from tests.test_account_expiry import _advance_after_row_lock, _queued_post
from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory
from tests.test_editor import editor as editor
from tests.test_editor import post, task_payload


@pytest.mark.parametrize("kind,locked_model", [
    ("guest", Guest), ("account", Guest), ("account", Account), ("account", AccessSession),
], ids=["guest-root", "account-root", "account", "access"])
def test_practice_rechecks_expiry_after_authorization_locks(
    account_factory, account_config, clock, kind, locked_model,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    if kind == "guest":
        assert client.post("/api/v1/guest", json={}).status_code == 200
        expiring_model = Guest
    else:
        login(client, mailbox)
        expiring_model = AccessSession
    database = client.app.state.database
    with database.transaction(write=True) as db:
        db.scalars(select(expiring_model)).one().expires_at = clock[0] + timedelta(seconds=1)

    with _advance_after_row_lock(database, clock, locked_model):
        response = client.post("/api/v1/sessions", json={
            "slots": [1], "length": 5, "mode": "practice",
        }, headers={"Idempotency-Key": str(uuid4())})

    assert response.status_code == 401, response.text
    with database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(LearningSessionRecord)) == 0
        assert db.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_guest_replaces_credential_expiring_after_root_lock(
    account_factory, account_config, clock,
):
    client = account_factory(config=account_config, mailbox=Mailbox())
    original = client.post("/api/v1/guest", json={}).json()["id"]
    credential = client.cookies.get("math_ege_guest")
    database = client.app.state.database
    with database.transaction(write=True) as db:
        db.get(Guest, original).expires_at = clock[0] + timedelta(seconds=1)

    with _advance_after_row_lock(database, clock, Guest):
        response = client.post("/api/v1/guest", json={})

    assert response.status_code == 200, response.text
    assert response.json()["id"] != original
    assert client.cookies.get("math_ege_guest") != credential
    with database.transaction() as db:
        assert db.get(Guest, response.json()["id"]).created_at == clock[0]
        assert db.get(Guest, original) is not None


def test_guest_cookie_lifetime_uses_post_writer_time(account_factory, account_config, clock):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    login(client, mailbox)
    credential = client.cookies.get("math_ege_guest")
    with client.app.state.database.transaction(write=True) as db:
        db.scalars(select(AccessSession)).one().expires_at = clock[0] + timedelta(seconds=10)

    response = _queued_post(client, clock, "/api/v1/guest", {})

    assert response.status_code == 200, response.text
    assert "Max-Age=8" in response.headers["set-cookie"]
    assert client.cookies.get("math_ege_guest") == credential


def test_new_guest_timestamp_uses_post_writer_time(account_factory, account_config, clock):
    client = account_factory(config=account_config, mailbox=Mailbox())
    response = _queued_post(client, clock, "/api/v1/guest", {})
    assert response.status_code == 200, response.text
    with client.app.state.database.transaction() as db:
        guest = db.get(Guest, response.json()["id"])
        assert guest.created_at == guest.last_seen_at == clock[0]


@pytest.mark.parametrize("expires", ["mfa", "session"])
def test_editor_reauthorizes_after_catalog_lock(editor, content, clock, monkeypatch, expires):
    from app.editor import service as editor_service

    client, identity = editor
    if expires == "session":
        with client.app.state.database.transaction(write=True) as db:
            db.get(AccessSession, identity.sessions["author"]).expires_at = (
                clock[0] + timedelta(seconds=900)
            )
    clock[0] += timedelta(seconds=899)
    lock_catalog = editor_service.lock_catalog

    def delayed_catalog_lock(db):
        catalog = lock_catalog(db)
        clock[0] += timedelta(seconds=2)
        return catalog

    monkeypatch.setattr(editor_service, "lock_catalog", delayed_catalog_lock)
    response = post(client, "/revisions", {
        "kind": "task", "payload": task_payload(content), "change_note": "Проверка срока доступа.",
    })

    assert response.status_code == (403 if expires == "mfa" else 401), response.text
    assert response.json()["error"]["code"] == (
        "mfa_required" if expires == "mfa" else "guest_required"
    )
    with client.app.state.database.transaction() as db:
        for model in (EditorRevision, EditorAudit, EditorPublication):
            assert db.scalar(select(func.count()).select_from(model)) == 0
