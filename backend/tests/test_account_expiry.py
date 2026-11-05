"""ACC-001: authorization deadlines must survive a queued database write."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Event

import pyotp
import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import postgresql

from app.accounts.authorization import authorize_staff
from app.accounts.models import (
    AccessSession,
    Account,
    AccountConsent,
    AccountDeletionRequest,
    GuestClaim,
    MagicLink,
    TotpCredential,
)
from app.accounts.principals import resolve_guest
from app.accounts.tokens import token_digest
from app.errors import ApiError
from app.models import Guest
from tests.test_accounts import Mailbox, login, request_link
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory


def _queued_post(client, clock, path, body):
    """Advance the injected clock only once the request reaches the held writer."""
    database = client.app.state.database
    waiting, acquired = Event(), Event()

    def before_begin(connection, cursor, statement, parameters, context, executemany):
        if statement == "BEGIN IMMEDIATE":
            waiting.set()

    def after_begin(connection, cursor, statement, parameters, context, executemany):
        if statement == "BEGIN IMMEDIATE":
            acquired.set()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with database.transaction(write=True):
                # Register after the holder's BEGIN, so only the queued request signals.
                event.listen(database.engine, "before_cursor_execute", before_begin)
                event.listen(database.engine, "after_cursor_execute", after_begin)
                pending = pool.submit(client.post, path, json=body)
                assert waiting.wait(timeout=10), "request did not reach the writer lock"
                assert not acquired.is_set() and not pending.done()
                clock[0] += timedelta(seconds=2)
            response = pending.result(timeout=10)
            assert acquired.is_set()
            return response
    finally:
        # The worker has finished before listeners are removed, including on assertion failure.
        event.remove(database.engine, "before_cursor_execute", before_begin)
        event.remove(database.engine, "after_cursor_execute", after_begin)


def _account_state(database):
    """Authentication/deletion effects; rejected attempts may still consume rate limits."""
    with database.transaction() as db:
        return {
            model.__tablename__: list(db.execute(
                select(model.__table__).order_by(*model.__table__.primary_key.columns),
            ).mappings())
            for model in (
                Guest, Account, GuestClaim, MagicLink, AccountConsent, AccessSession,
                TotpCredential, AccountDeletionRequest,
            )
        }


@contextmanager
def _advance_after_row_lock(database, clock, model, occurrence=1):
    """Model elapsed time at a PostgreSQL lock boundary, using the real ORM queries.

    SQLite ignores FOR UPDATE; this checks clock ordering, not live PostgreSQL contention.
    """
    seen = 0

    def after_lock(connection, cursor, statement, parameters, context, executemany):
        nonlocal seen
        if (
            context.compiled is not None and statement.startswith("SELECT ")
            and f"FROM {model.__tablename__}" in statement
            and str(context.compiled.statement.compile(dialect=postgresql.dialect()))
            .endswith("FOR UPDATE")
        ):
            seen += 1
            if seen == occurrence:
                clock[0] += timedelta(seconds=2)

    event.listen(database.engine, "after_cursor_execute", after_lock)
    try:
        yield
        assert seen >= occurrence, "request did not acquire the expected authorization lock"
    finally:
        event.remove(database.engine, "after_cursor_execute", after_lock)


def test_link_expiring_behind_writer_does_not_authenticate_or_claim(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    assert client.post("/api/v1/guest", json={}).status_code == 200
    cookie = client.cookies.get("math_ege_guest")
    link = request_link(client, mailbox)
    before = _account_state(client.app.state.database)
    clock[0] += timedelta(seconds=899)

    response = _queued_post(client, clock, "/api/v1/auth/complete", {"token": link})

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_link"
    assert "set-cookie" not in response.headers
    assert client.cookies.get("math_ege_guest") == cookie
    assert _account_state(client.app.state.database) == before
    assert client.get("/api/v1/account").status_code == 401


def test_login_recency_expiring_behind_writer_does_not_enroll_mfa(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    login(client, mailbox)
    cookie = client.cookies.get("math_ege_guest")
    before = _account_state(client.app.state.database)
    clock[0] += timedelta(seconds=899)

    response = _queued_post(client, clock, "/api/v1/auth/mfa/enroll", {})

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "recent_login_required"
    assert "set-cookie" not in response.headers
    assert client.cookies.get("math_ege_guest") == cookie
    assert _account_state(client.app.state.database) == before
    assert client.get("/api/v1/account").json()["mfa_enabled"] is False


@pytest.mark.parametrize("locked_model", [None, Guest, AccessSession, TotpCredential], ids=[
    "writer-begin", "root-lock", "access-lock", "mfa-lock",
])
def test_totp_expiring_during_lock_wait_does_not_elevate_or_rotate_session(
    account_factory, account_config, clock, monkeypatch, locked_model,
):
    # A fixed test secret avoids accidental equal six-digit codes in different ticks.
    monkeypatch.setattr(pyotp, "random_base32", lambda: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP")
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    account = login(client, mailbox)
    enrollment = client.post("/api/v1/auth/mfa/enroll", json={})
    assert enrollment.status_code == 200, enrollment.text
    authenticator = pyotp.TOTP(enrollment.json()["secret"])
    confirmed_at = clock[0]
    confirmed = client.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(confirmed_at)},
    )
    assert confirmed.status_code == 200, confirmed.text
    cookie = client.cookies.get("math_ege_guest")
    code = authenticator.at(confirmed_at + timedelta(seconds=30))
    clock[0] += timedelta(seconds=89)
    assert authenticator.verify(code, for_time=clock[0], valid_window=1)

    if locked_model is None:
        response = _queued_post(client, clock, "/api/v1/auth/mfa/verify", {"code": code})
    else:
        with _advance_after_row_lock(client.app.state.database, clock, locked_model):
            response = client.post("/api/v1/auth/mfa/verify", json={"code": code})

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_mfa"
    assert not authenticator.verify(code, for_time=clock[0], valid_window=1)
    assert "set-cookie" not in response.headers
    assert client.cookies.get("math_ege_guest") == cookie
    with client.app.state.database.transaction() as db:
        access = db.scalars(select(AccessSession)).one()
        assert access.token_digest == token_digest(cookie)
        assert access.mfa_verified_at == confirmed_at
        assert access.revoked_at is None
        record = db.get(TotpCredential, account["id"])
        assert record.confirmed_at == confirmed_at
        assert record.last_timecode == authenticator.timecode(confirmed_at)
        assert record.attempts == [confirmed_at.timestamp(), clock[0].timestamp()]


def test_session_expiring_behind_writer_does_not_request_deletion(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    login(client, mailbox)
    cookie = client.cookies.get("math_ege_guest")
    with client.app.state.database.transaction(write=True) as db:
        db.scalars(select(AccessSession)).one().expires_at = clock[0] + timedelta(seconds=1)
    before = _account_state(client.app.state.database)

    response = _queued_post(
        client, clock, "/api/v1/account/deletion-request", {"confirm": True},
    )

    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "guest_required"
    assert "set-cookie" not in response.headers
    assert client.cookies.get("math_ege_guest") == cookie
    assert _account_state(client.app.state.database) == before
    assert client.get("/api/v1/account").status_code == 401


@pytest.mark.parametrize("locked_model,occurrence", [
    (MagicLink, 1), (Guest, 1), (Account, 1), (AccessSession, 1), (AccessSession, 2),
], ids=["link", "root", "account", "old-access", "active-access"])
def test_link_expiring_after_row_locks_does_not_consume_or_revoke(
    account_factory, account_config, clock, locked_model, occurrence,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    login(client, mailbox)
    cookie = client.cookies.get("math_ege_guest")
    link = request_link(client, mailbox)
    before = _account_state(client.app.state.database)
    clock[0] += timedelta(seconds=899)

    with _advance_after_row_lock(client.app.state.database, clock, locked_model, occurrence):
        response = client.post("/api/v1/auth/complete", json={"token": link})

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "invalid_link"
    assert "set-cookie" not in response.headers
    assert client.cookies.get("math_ege_guest") == cookie
    assert _account_state(client.app.state.database) == before
    assert client.get("/api/v1/account").status_code == 200


@pytest.mark.parametrize("kind,locked_model", [
    ("guest", Guest), ("account", Guest), ("account", Account), ("account", AccessSession),
], ids=["guest-root", "account-root", "account", "access"])
def test_resolver_rechecks_expiry_after_row_locks(
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
    cookie = client.cookies.get("math_ege_guest")
    with database.transaction(write=True) as db:
        db.scalars(select(expiring_model)).one().expires_at = clock[0] + timedelta(seconds=1)
    before = _account_state(database)
    sampled_at = clock[0]

    with (
        _advance_after_row_lock(database, clock, locked_model),
        pytest.raises(ApiError) as rejected,
        database.transaction(write=True) as db,
    ):
        resolve_guest(db, cookie, sampled_at, True, clock=client.app.state.accounts.clock)

    assert rejected.value.status_code == 401
    assert _account_state(database) == before


@pytest.mark.parametrize("expires", ["mfa", "session"])
def test_staff_gate_rechecks_deadlines_after_mfa_row_lock(
    account_factory, account_config, clock, expires,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    account = login(client, mailbox)
    enrollment = client.post("/api/v1/auth/mfa/enroll", json={})
    assert enrollment.status_code == 200, enrollment.text
    authenticator = pyotp.TOTP(enrollment.json()["secret"])
    assert client.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])},
    ).status_code == 200
    database = client.app.state.database
    with database.transaction(write=True) as db:
        db.get(Account, account["id"]).role = "admin"
        if expires == "session":
            db.scalars(select(AccessSession)).one().expires_at = clock[0] + timedelta(seconds=900)
    before = _account_state(database)
    cookie = client.cookies.get("math_ege_guest")
    clock[0] += timedelta(seconds=899)

    with (
        _advance_after_row_lock(database, clock, TotpCredential),
        pytest.raises(ApiError) as rejected,
        database.transaction(write=True) as db,
    ):
        authorize_staff(
            db, cookie, clock[0], write=True, clock=client.app.state.accounts.clock,
        )

    assert rejected.value.status_code == (403 if expires == "mfa" else 401)
    assert rejected.value.code == ("mfa_required" if expires == "mfa" else "guest_required")
    assert _account_state(database) == before
