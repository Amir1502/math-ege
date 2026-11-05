"""Account behavior through the real HTTP app and isolated delivery/database seams."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from shutil import copyfile
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pyotp
import pytest
from cryptography.fernet import Fernet

from tests.helpers import answer, draft, expected, start
from tests.test_concurrency import race


class Mailbox:
    def __init__(self):
        self.messages = []

    def send_login_link(self, email, link, expires_at):
        self.messages.append((email, link, expires_at))


@pytest.fixture
def account_config():
    from app.accounts.config import AccountSettings

    return AccountSettings(
        enabled=True, policy_approved=True, policy_version="test-1",
        policy_url="https://example.org/privacy", public_origin="http://testserver",
        mfa_encryption_key=Fernet.generate_key().decode("ascii"),
    )


@pytest.fixture
def account_factory(client_factory):
    def make(*, config=None, mailbox=None, **overrides):
        from app.accounts.api import router
        from app.accounts.config import AccountSettings
        from app.accounts.service import AccountService

        client = client_factory(environment="test", **overrides)
        if not hasattr(client.app.state, "accounts"):
            client.app.include_router(router)
        client.app.state.accounts = AccountService(
            client.app.state.service,
            config=config or AccountSettings(),
            mail_sender=mailbox,
        )
        client.app.state.database.create_schema_for_tests()
        return client

    return make


def test_accounts_are_disabled_without_explicit_policy_and_delivery(account_factory):
    client = account_factory()
    assert client.get("/api/v1/auth/config").json() == {
        "enabled": False,
        "policy_version": None,
        "policy_url": None,
        "link_ttl_seconds": 900,
    }
    response = client.post(
        "/api/v1/auth/request-link",
        json={"email": "student@example.org", "policy_version": "test-1", "accept_policy": True},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "accounts_disabled"
    assert "set-cookie" not in response.headers
    assert client.post("/api/v1/guest", json={}).status_code == 200


def request_link(client, mailbox, email="student@example.org", policy_version="test-1"):
    response = client.post(
        "/api/v1/auth/request-link",
        json={"email": email, "policy_version": policy_version, "accept_policy": True},
    )
    assert response.status_code == 202, response.text
    return parse_qs(urlsplit(mailbox.messages[-1][1]).fragment)["token"][0]


def test_email_link_establishes_a_verified_session_once_without_exposing_tokens(
    account_factory, account_config, clock, caplog,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    guest_id = client.post("/api/v1/guest", json={}).json()["id"]
    guest_cookie = client.cookies.get("math_ege_guest")
    link_token = request_link(client, mailbox, " Student@EXAMPLE.org ")
    recipient, link, expires_at = mailbox.messages[-1]
    assert recipient == "student@example.org"
    assert urlsplit(link).query == ""
    assert expires_at.timestamp() - clock[0].timestamp() == 900
    assert client.get("/api/v1/auth/complete").status_code == 405

    response = client.post("/api/v1/auth/complete", json={"token": link_token})
    assert response.status_code == 200, response.text
    account = response.json()
    assert account["email"] == recipient
    assert account["email_verified"] is True
    assert account["role"] == "student"
    assert guest_id in account["owner_ids"]
    assert account["mfa_enabled"] is False
    assert account["mfa_verified_until"] is None
    access_cookie = client.cookies.get("math_ege_guest")
    assert access_cookie and access_cookie != guest_cookie
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/account").json() == account
    assert client.post("/api/v1/auth/complete", json={"token": link_token}).status_code == 400
    for secret in (link_token, access_cookie, guest_cookie):
        assert secret not in response.text
        assert secret not in caplog.text


def login(client, mailbox, email="student@example.org"):
    link_token = request_link(client, mailbox, email)
    response = client.post("/api/v1/auth/complete", json={"token": link_token})
    assert response.status_code == 200, response.text
    return response.json()


def test_claims_combine_history_without_copying_attempts_or_losing_pending_drafts(
    account_factory, account_config, content,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    first_guest = first.post("/api/v1/guest", json={}).json()["id"]
    stale_token = first.cookies.get("math_ege_guest")
    session = start(first).json()
    attempt = answer(
        first, session, session["tasks"][0], expected(content, session["tasks"][0]),
    ).json()
    pending_task = session["tasks"][1]
    assert draft(first, session, pending_task, "12,").status_code == 200
    before = first.get("/api/v1/export").json()["sessions"]
    account = login(first, mailbox)

    shared = {"config": account_config, "mailbox": mailbox,
              "database_url": first.app.state.settings.database_url}
    second = account_factory(**shared)
    second_guest = second.post("/api/v1/guest", json={}).json()["id"]
    second_session = start(second).json()
    second_attempt = answer(second, second_session, second_session["tasks"][0], "42").json()
    assert login(second, mailbox)["id"] == account["id"]
    assert login(second, mailbox)["id"] == account["id"]

    response = first.get("/api/v1/account/export")
    assert response.status_code == 200, response.text
    exported = response.json()
    sessions = {item["id"]: item for item in exported["sessions"]}
    assert sessions[session["id"]] == before[0]
    assert sessions[session["id"]]["drafts"][pending_task["id"]]["answer"] == "12,"
    assert {item["id"] for item in sessions.values()} == {session["id"], second_session["id"]}
    exported_attempt_ids = sorted(
        item["id"] for saved in sessions.values() for item in saved["attempts"]
    )
    assert exported_attempt_ids == sorted([attempt["id"], second_attempt["id"]])
    assert set(exported["account"]["owner_ids"]) == {
        account["root_guest_id"], first_guest, second_guest,
    }
    assert len(exported["consents"]) == 1
    for forbidden in ("token_digest", "browser_state", "secret", "ciphertext", "mfa_attempts"):
        assert forbidden not in response.text

    stale = account_factory(**shared)
    stale.cookies.set("math_ege_guest", stale_token)
    assert stale.get("/api/v1/account/export").status_code == 401
    assert stale.post("/api/v1/guest", json={}).json()["id"] not in exported["account"]["owner_ids"]
    outsider = account_factory(**shared)
    other = login(outsider, mailbox, "other@example.org")
    assert other["id"] != account["id"]
    assert outsider.get("/api/v1/account/export").json()["sessions"] == []
    assert set(other["owner_ids"]).isdisjoint(exported["account"]["owner_ids"])


def test_link_is_bound_to_both_the_browser_state_and_original_credential(
    account_factory, account_config,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    first.post("/api/v1/guest", json={})
    link_token = request_link(first, mailbox)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    second.cookies.set("math_ege_guest", first.cookies.get("math_ege_guest"))
    assert second.post("/api/v1/auth/complete", json={"token": link_token}).status_code == 400
    second.cookies.clear()
    second_guest = second.post("/api/v1/guest", json={}).json()["id"]
    second.cookies.set("math_ege_auth_state", first.cookies.get("math_ege_auth_state"))
    assert second.post("/api/v1/auth/complete", json={"token": link_token}).status_code == 400
    assert first.post(
        "/api/v1/auth/complete", json={"token": link_token, "guest_id": second_guest},
    ).status_code == 422
    assert first.post("/api/v1/auth/complete", json={"token": link_token}).status_code == 200


def test_link_expiry_is_enforced_at_fifteen_minutes(account_factory, account_config, clock):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    link_token = request_link(client, mailbox)
    clock[0] += timedelta(minutes=15)
    expired = client.post("/api/v1/auth/complete", json={"token": link_token})
    invalid = client.post("/api/v1/auth/complete", json={"token": "x" * 43})
    assert expired.status_code == invalid.status_code == 400
    assert expired.json() == invalid.json()
    assert client.get("/api/v1/account").status_code == 401


def test_email_limit_is_generic_rolling_and_survives_app_restart(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    body = {"email": "student@example.org", "policy_version": "test-1", "accept_policy": True}
    replies = [first.post("/api/v1/auth/request-link", json=body) for _ in range(5)]
    assert len(mailbox.messages) == 5
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    clock[0] += timedelta(minutes=59, seconds=59)
    replies.append(second.post(
        "/api/v1/auth/request-link", json={**body, "email": "STUDENT@EXAMPLE.ORG"},
    ))
    assert len(mailbox.messages) == 5
    assert all(reply.status_code == 202 and reply.json() == replies[0].json() for reply in replies)
    assert "student@example.org" not in replies[0].text
    assert set(replies[0].json()) == {"message"}
    clock[0] += timedelta(seconds=1)
    assert second.post("/api/v1/auth/request-link", json=body).status_code == 202
    assert len(mailbox.messages) == 6


def test_email_limits_are_atomic_across_workers(account_factory, account_config):
    mailbox = Mailbox()
    first = account_factory(config=account_config, mailbox=mailbox)
    second = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=first.app.state.settings.database_url,
    )
    # Build lazy route schemas before FastAPI's warning contexts run in parallel.
    for client in (first, second):
        assert client.get("/api/v1/auth/config").status_code == 200
    body = {"email": "student@example.org", "policy_version": "test-1", "accept_policy": True}
    replies = race(*(
        lambda client=client: client.post("/api/v1/auth/request-link", json=body)
        for client in (first, second) * 3
    ))
    assert all(reply.status_code == 202 for reply in replies)
    assert len(mailbox.messages) == 5


def test_global_email_limit_bounds_requests_across_new_addresses(account_factory, account_config):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    for index in range(101):
        response = client.post("/api/v1/auth/request-link", json={
            "email": f"student-{index}@example.org",
            "policy_version": "test-1", "accept_policy": True,
        })
        assert response.status_code == 202
    assert len(mailbox.messages) == 100


def test_mail_failure_does_not_disclose_recipient_token_or_delivery_status(
    account_factory, account_config, caplog,
):
    class BrokenMail(Mailbox):
        def send_login_link(self, email, link, expires_at):
            super().send_login_link(email, link, expires_at)
            raise TimeoutError(f"SMTP failed: {email} {link}")

    mailbox = BrokenMail()
    client = account_factory(config=account_config, mailbox=mailbox)
    link_token = request_link(client, mailbox)
    assert link_token not in caplog.text
    assert mailbox.messages[0][0] not in caplog.text
    assert "TimeoutError" in caplog.text


def test_secure_cookies_and_same_origin_mutations(account_factory, account_config):
    mailbox = Mailbox()
    client = account_factory(
        config=replace(account_config, public_origin="https://testserver"), mailbox=mailbox,
        cookie_secure=True, allowed_origins=("https://testserver",),
    )
    client.base_url = "https://testserver"
    client.headers["Origin"] = "https://testserver"
    link_token = request_link(client, mailbox)
    state_cookie = next(
        cookie for cookie in client.cookies.jar if cookie.name == "math_ege_auth_state"
    )
    assert state_cookie.secure
    assert client.post(
        "/api/v1/auth/complete", json={"token": link_token}, headers={"Origin": "https://foreign.example"},
    ).status_code == 403
    response = client.post("/api/v1/auth/complete", json={"token": link_token})
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()
    assert next(cookie for cookie in client.cookies.jar if cookie.name == "math_ege_guest").secure


def test_competing_guest_claims_never_connect_two_accounts(account_factory, account_config):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    one.post("/api/v1/guest", json={})
    original = start(one).json()
    two = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=one.app.state.settings.database_url,
    )
    two.cookies.set("math_ege_guest", one.cookies.get("math_ege_guest"))
    links = [
        request_link(one, mailbox, "one@example.org"),
        request_link(two, mailbox, "two@example.org"),
    ]
    replies = race(*(
        lambda client=client, link=link: client.post("/api/v1/auth/complete", json={"token": link})
        for client, link in zip((one, two), links, strict=True)
    ))
    assert sorted(reply.status_code for reply in replies) == [200, 400]
    winner_index = 0 if replies[0].status_code == 200 else 1
    winner, loser = ((one, two) if winner_index == 0 else (two, one))
    assert winner.get("/api/v1/account/export").json()["sessions"][0]["id"] == original["id"]
    loser_email = "two@example.org" if winner_index == 0 else "one@example.org"
    losing_account = login(loser, mailbox, loser_email)
    assert loser.get("/api/v1/account/export").json()["sessions"] == []
    assert set(losing_account["owner_ids"]).isdisjoint(replies[winner_index].json()["owner_ids"])


def test_account_sessions_are_owner_scoped_and_logout_revokes_the_bearer(
    account_factory, account_config,
):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    login(one, mailbox)
    shared = {"config": account_config, "mailbox": mailbox,
              "database_url": one.app.state.settings.database_url}
    two = account_factory(**shared)
    login(two, mailbox)
    response = two.get("/api/v1/account/sessions")
    assert response.status_code == 200, response.text
    sessions = response.json()["sessions"]
    assert len(sessions) == 2
    assert sum(session["current"] for session in sessions) == 1
    old_id = next(session["id"] for session in sessions if not session["current"])
    outsider = account_factory(**shared)
    login(outsider, mailbox, "other@example.org")
    assert outsider.post(f"/api/v1/account/sessions/{old_id}/revoke", json={}).status_code == 404
    assert one.get("/api/v1/account").status_code == 200
    assert two.post(f"/api/v1/account/sessions/{old_id}/revoke", json={}).json() == {"ok": True}
    assert one.get("/api/v1/account").status_code == 401
    saved_token = two.cookies.get("math_ege_guest")
    assert two.post("/api/v1/auth/logout", json={}).json() == {"ok": True}
    assert two.get("/api/v1/account").status_code == 401
    assert two.post("/api/v1/auth/logout", json={}).status_code == 200
    one.cookies.clear()
    one.cookies.set("math_ege_guest", saved_token)
    assert one.get("/api/v1/account").status_code == 401
    assert "token" not in response.text and "email" not in response.text


def test_account_preferences_are_shared_but_privileged_properties_are_not_editable(
    account_factory, account_config,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    login(client, mailbox)
    response = client.patch("/api/v1/account", json={"daily_minutes": 30})
    assert response.status_code == 200, response.text
    assert response.json()["daily_minutes"] == 30
    assert client.get("/api/v1/account").json()["daily_minutes"] == 30
    for payload in ({"role": "admin"}, {"email_verified": True}, {"email": "other@example.org"},
                    {"daily_minutes": "30"}, {"daily_minutes": 30.0}, {"daily_minutes": 0}):
        assert client.patch("/api/v1/account", json=payload).status_code == 422
    assert client.get("/api/v1/account").json()["role"] == "student"


def test_deletion_request_has_a_fixed_deadline_and_never_executes_deletion(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    client.post("/api/v1/guest", json={})
    start(client)
    login(client, mailbox)
    before = client.get("/api/v1/account/export").json()["sessions"]
    status = client.get("/api/v1/account/deletion-request")
    assert status.status_code == 200, status.text
    assert status.json() == {"request": None}
    assert client.post(
        "/api/v1/account/deletion-request", json={"confirm": False},
    ).status_code == 422
    response = client.post("/api/v1/account/deletion-request", json={"confirm": True})
    assert response.status_code == 200, response.text
    request = response.json()["request"]
    assert request["status"] == "requested"
    deadline = datetime.fromisoformat(request["deadline_at"])
    assert clock[0] < deadline <= clock[0] + timedelta(days=30)
    clock[0] += timedelta(days=1)
    assert client.post(
        "/api/v1/account/deletion-request", json={"confirm": True},
    ).json() == response.json()
    assert client.get("/api/v1/account/deletion-request").json() == response.json()
    exported = client.get("/api/v1/account/export").json()
    assert exported["sessions"] == before
    assert exported["deletion_request"] == request
    assert client.get("/api/v1/account").status_code == 200


def test_mfa_enrollment_confirms_possession_rotates_cookie_and_cannot_grant_a_role(
    account_factory, account_config, clock, caplog,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    login(client, mailbox)
    old_cookie = client.cookies.get("math_ege_guest")
    response = client.post("/api/v1/auth/mfa/enroll", json={})
    assert response.status_code == 200, response.text
    enrollment = response.json()
    authenticator = pyotp.parse_uri(enrollment["provisioning_uri"])
    assert authenticator.secret == enrollment["secret"]
    assert datetime.fromisoformat(enrollment["expires_at"]) == clock[0] + timedelta(minutes=10)
    assert client.get("/api/v1/account").json()["mfa_enabled"] is False
    confirmed = client.post("/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["enabled"] is True
    assert client.cookies.get("math_ege_guest") != old_cookie
    account = client.get("/api/v1/account").json()
    assert account["role"] == "student"
    assert account["mfa_enabled"] is True
    assert datetime.fromisoformat(account["mfa_verified_until"]) == clock[0] + timedelta(minutes=15)
    assert client.post("/api/v1/auth/mfa/enroll", json={"role": "admin"}).status_code == 422
    assert client.post("/api/v1/auth/mfa/enroll", json={}).status_code == 409
    assert client.post(
        "/api/v1/auth/mfa/verify", json={"code": authenticator.at(clock[0])},
    ).status_code == 400
    assert enrollment["secret"] not in client.get("/api/v1/account/export").text
    assert enrollment["secret"] not in caplog.text
    stale = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=client.app.state.settings.database_url,
    )
    stale.cookies.set("math_ege_guest", old_cookie)
    assert stale.get("/api/v1/account").status_code == 401


def staff_routes(app):
    from fastapi import Request

    from app.accounts import require_staff

    @app.post("/_test/staff/edit")
    def edit(request: Request):
        principal = require_staff(request)
        return {"account_id": principal.account_id, "role": principal.role}

    @app.post("/_test/staff/publish")
    def publish(request: Request):
        principal = require_staff(request, publish=True)
        return {"account_id": principal.account_id, "role": principal.role}


@pytest.mark.parametrize("role,publication_status", [("methodist", 403), ("admin", 200)])
def test_staff_roles_require_recent_mfa_and_only_admin_can_publish(
    account_factory, account_config, clock, role, publication_status,
):
    from app.accounts.bootstrap import assign_role

    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    staff_routes(client.app)
    assert client.post("/_test/staff/edit", json={}).status_code == 401
    account = login(client, mailbox)
    assert client.post("/_test/staff/edit", json={}).status_code == 403
    with pytest.raises(ValueError, match="MFA"):
        assign_role(
            client.app.state.database, email=account["email"], role=role,
            operator="isolated-test", now=clock[0],
        )
    enrollment = client.post("/api/v1/auth/mfa/enroll", json={}).json()
    authenticator = pyotp.TOTP(enrollment["secret"])
    assert client.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])},
    ).status_code == 200
    assert client.post("/_test/staff/edit", json={}).status_code == 403
    assign_role(
        client.app.state.database, email=account["email"], role=role,
        operator="isolated-test", now=clock[0],
    )
    assert client.get("/api/v1/account").status_code == 401
    assert login(client, mailbox)["role"] == role
    assert client.post("/_test/staff/edit", json={}).json()["error"]["code"] == "mfa_required"
    clock[0] += timedelta(seconds=30)
    assert client.post(
        "/api/v1/auth/mfa/verify", json={"code": authenticator.at(clock[0])},
    ).status_code == 200
    assert client.post("/_test/staff/edit", json={}).json() == {
        "account_id": account["id"], "role": role,
    }
    assert client.post("/_test/staff/publish", json={}).status_code == publication_status
    clock[0] += timedelta(minutes=15)
    assert client.post("/_test/staff/edit", json={}).json()["error"]["code"] == "mfa_required"


def test_failed_mfa_attempts_persist_across_sessions_and_restart(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    login(one, mailbox)
    enrollment = one.post("/api/v1/auth/mfa/enroll", json={}).json()
    authenticator = pyotp.TOTP(enrollment["secret"])
    valid_code = authenticator.at(clock[0])
    wrong_code = next(
        f"{value:06d}" for value in range(10)
        if not authenticator.verify(f"{value:06d}", for_time=clock[0], valid_window=1)
    )
    for _ in range(5):
        assert one.post("/api/v1/auth/mfa/confirm", json={"code": wrong_code}).status_code == 400
    two = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=one.app.state.settings.database_url,
    )
    two.cookies.set("math_ege_guest", one.cookies.get("math_ege_guest"))
    assert two.post("/api/v1/auth/mfa/confirm", json={"code": valid_code}).status_code == 429
    clock[0] += timedelta(minutes=5)
    assert two.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])},
    ).status_code == 200


def test_mfa_replay_is_rejected_between_concurrent_sessions(account_factory, account_config, clock):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    login(one, mailbox)
    enrollment = one.post("/api/v1/auth/mfa/enroll", json={}).json()
    authenticator = pyotp.TOTP(enrollment["secret"])
    assert one.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])},
    ).status_code == 200
    two = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=one.app.state.settings.database_url,
    )
    login(two, mailbox)
    clock[0] += timedelta(seconds=30)
    code = authenticator.at(clock[0])
    replies = race(*(
        lambda client=client: client.post("/api/v1/auth/mfa/verify", json={"code": code})
        for client in (one, two)
    ))
    assert sorted(reply.status_code for reply in replies) == [200, 400]


def test_mfa_enrollment_requires_a_recent_login_and_the_initiating_session(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    login(one, mailbox)
    enrollment = one.post("/api/v1/auth/mfa/enroll", json={}).json()
    authenticator = pyotp.TOTP(enrollment["secret"])
    two = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=one.app.state.settings.database_url,
    )
    login(two, mailbox)
    assert two.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])},
    ).status_code == 400
    clock[0] += timedelta(minutes=10)
    assert one.post(
        "/api/v1/auth/mfa/confirm", json={"code": authenticator.at(clock[0])},
    ).status_code == 400
    clock[0] += timedelta(minutes=5)
    response = one.post("/api/v1/auth/mfa/enroll", json={})
    assert response.json()["error"]["code"] == "recent_login_required"


def test_bearers_and_mfa_secret_are_not_stored_in_plaintext(account_factory, account_config):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    link_token = request_link(client, mailbox)
    state = client.cookies.get("math_ege_auth_state")
    assert client.post("/api/v1/auth/complete", json={"token": link_token}).status_code == 200
    access_token = client.cookies.get("math_ege_guest")
    secret = client.post("/api/v1/auth/mfa/enroll", json={}).json()["secret"]
    database_bytes = Path(client.app.state.settings.database_url.removeprefix("sqlite:///")).read_bytes()
    for value in (link_token, state, access_token, secret, account_config.mfa_encryption_key):
        assert value.encode("ascii") not in database_bytes
    assert account_config.mfa_encryption_key not in repr(account_config)


@pytest.mark.parametrize("change", [
    {"enabled": False}, {"policy_approved": False}, {"policy_version": None},
    {"policy_url": None}, {"public_origin": None},
])
def test_injected_mail_never_bypasses_the_policy_gate(account_factory, account_config, change):
    mailbox = Mailbox()
    client = account_factory(config=replace(account_config, **change), mailbox=mailbox)
    assert client.get("/api/v1/auth/config").json()["enabled"] is False
    response = client.post("/api/v1/auth/request-link", json={
        "email": "student@example.org", "policy_version": "test-1", "accept_policy": True,
    })
    assert response.status_code == 503
    assert mailbox.messages == []


def test_missing_delivery_and_mfa_key_fail_closed(account_factory, account_config):
    client = account_factory(config=account_config)
    assert client.get("/api/v1/auth/config").json()["enabled"] is False
    mailbox = Mailbox()
    client = account_factory(
        config=replace(account_config, mfa_encryption_key=None), mailbox=mailbox,
    )
    login(client, mailbox)
    assert client.post("/api/v1/auth/mfa/enroll", json={}).status_code == 503


def test_access_session_expiry_does_not_depend_on_guest_expiry(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox, guest_access_days=1)
    client.post("/api/v1/guest", json={})
    login(client, mailbox)
    clock[0] += timedelta(days=2)
    assert client.get("/api/v1/account").status_code == 200
    clock[0] += timedelta(days=28)
    assert client.get("/api/v1/account").status_code == 401


def test_account_migration_preserves_populated_learning_tables_and_refuses_downgrade(
    tmp_path, clock,
):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import MetaData, inspect, null, select

    from app.config import Settings
    from app.database import Database

    backend = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "account-migrations"
    versions = scripts / "versions"
    versions.mkdir(parents=True)
    copyfile(backend / "migrations" / "env.py", scripts / "env.py")
    for name in ("0001_learning_core.py", "0002_accounts.py"):
        copyfile(backend / "migrations" / "versions" / name, versions / name)
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(scripts))
    url = f"sqlite:///{(tmp_path / 'accounts-migration.sqlite3').as_posix()}"
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "0001_learning_core")
    database = Database(Settings(database_url=url))
    guest_id, session_id = str(uuid4()), str(uuid4())
    now = clock[0]
    try:
        # Seed the historical schema, independently of columns added after 0002.
        legacy = MetaData()
        legacy.reflect(bind=database.engine, only=(
            "guests", "learning_sessions", "attempts", "seen_tasks", "idempotency_records",
        ))
        tables = legacy.tables
        with database.transaction(write=True) as db:
            db.execute(tables["guests"].insert().values(
                id=guest_id, token_digest="a" * 64, created_at=now,
                expires_at=now + timedelta(days=180), last_seen_at=now,
            ))
            db.execute(tables["learning_sessions"].insert().values(
                id=session_id, guest_id=guest_id,
                profile_id="historic-profile", profile_revision="v1",
                profile_snapshot={"id": "historic-profile"}, mode="practice", status="active",
                created_at=now, completed_at=None, current_index=0, requested_length=5, notice=None,
                draft_revision=1, tasks_snapshot=[], drafts={"old-task": {"answer": "12,"}},
                help_state={}, active_seconds={}, summary_snapshot=null(),
            ))
            db.execute(tables["attempts"].insert().values(
                id=str(uuid4()), guest_id=guest_id, session_id=session_id, task_id="old-task",
                task_revision="v1", sequence=0, raw_answer="1/2", normalized_answer="0,5",
                correct=True, assisted=False, first_attempt=True, independent=True, skipped=False,
                active_seconds=17, created_at=now, checker_revision="fraction-v1",
                expected_answer="0,5", solution=["Сократите дробь."],
            ))
            db.execute(tables["seen_tasks"].insert().values(
                id=str(uuid4()), guest_id=guest_id, task_id="old-task", first_seen_at=now,
                last_seen_at=now, assistance_seen=False, reference_seen=True,
            ))
            db.execute(tables["idempotency_records"].insert().values(
                id=str(uuid4()), guest_id=guest_id, request_key=str(uuid4()), request_hash="b" * 64,
                operation=f"POST /sessions/{session_id}/attempts", status_code=200,
                response_json='{"id":"historic-feedback"}', created_at=now,
            ))

        def snapshot():
            with database.engine.connect() as connection:
                return {
                    name: list(connection.execute(select(table)).mappings())
                    for name, table in tables.items()
                }

        before = snapshot()
        command.upgrade(config, "0002_accounts")
        assert snapshot() == before
        assert {
            "accounts", "guest_claims", "access_sessions", "account_magic_links",
            "account_rate_limits", "account_consents", "account_deletion_requests",
            "account_totp_credentials", "account_role_audit",
        } <= set(inspect(database.engine).get_table_names())
        with pytest.raises(RuntimeError, match="disabled"):
            command.downgrade(config, "0001_learning_core")
        assert snapshot() == before
    finally:
        database.dispose()


def test_one_link_can_only_complete_once_across_workers(account_factory, account_config):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    link_token = request_link(one, mailbox)
    two = account_factory(
        config=account_config, mailbox=mailbox,
        database_url=one.app.state.settings.database_url,
    )
    two.cookies.set("math_ege_auth_state", one.cookies.get("math_ege_auth_state"))
    replies = race(*(
        lambda client=client: client.post("/api/v1/auth/complete", json={"token": link_token})
        for client in (one, two)
    ))
    assert sorted(reply.status_code for reply in replies) == [200, 400]
    winner = one if replies[0].status_code == 200 else two
    assert len(winner.get("/api/v1/account/sessions").json()["sessions"]) == 1


def test_policy_update_requires_fresh_consent_and_rejects_older_links(
    account_factory, account_config,
):
    mailbox = Mailbox()
    one = account_factory(config=account_config, mailbox=mailbox)
    login(one, mailbox)
    old_link = request_link(one, mailbox)
    two = account_factory(
        config=replace(account_config, policy_version="test-2"), mailbox=mailbox,
        database_url=one.app.state.settings.database_url,
    )
    two.cookies.set("math_ege_guest", one.cookies.get("math_ege_guest"))
    two.cookies.set("math_ege_auth_state", one.cookies.get("math_ege_auth_state"))
    assert two.post("/api/v1/auth/complete", json={"token": old_link}).status_code == 400
    for policy, accepted in (("test-1", True), ("test-2", False)):
        assert two.post("/api/v1/auth/request-link", json={
            "email": "student@example.org", "policy_version": policy, "accept_policy": accepted,
        }).status_code == 422
    new_link = request_link(two, mailbox, policy_version="test-2")
    assert two.post("/api/v1/auth/complete", json={"token": new_link}).status_code == 200
    exported = two.get("/api/v1/account/export").json()
    assert exported["account"]["policy_version"] == "test-2"
    assert {consent["policy_version"] for consent in exported["consents"]} == {"test-1", "test-2"}


def test_active_session_cap_revokes_the_oldest_and_current_revoke_clears_cookie(
    account_factory, account_config, clock,
):
    mailbox = Mailbox()
    oldest = account_factory(config=account_config, mailbox=mailbox)
    login(oldest, mailbox)
    newest = oldest
    for _ in range(10):
        clock[0] += timedelta(hours=1)
        newest = account_factory(
            config=account_config, mailbox=mailbox,
            database_url=oldest.app.state.settings.database_url,
        )
        login(newest, mailbox)
    assert oldest.get("/api/v1/account").status_code == 401
    sessions = newest.get("/api/v1/account/sessions").json()["sessions"]
    assert len(sessions) == 10
    current = next(session["id"] for session in sessions if session["current"])
    assert newest.post(f"/api/v1/account/sessions/{current}/revoke", json={}).status_code == 200
    assert newest.cookies.get("math_ege_guest") is None
    assert newest.get("/api/v1/account").status_code == 401
