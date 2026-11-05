from uuid import uuid4

import pytest

from tests.test_accounts import Mailbox, login
from tests.test_accounts import account_config as account_config
from tests.test_accounts import account_factory as account_factory


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/account", None),
    ("PATCH", "/account", {"daily_minutes": 30}),
    ("GET", "/account/export", None),
    ("GET", "/account/sessions", None),
    ("GET", "/account/deletion-request", None),
    ("POST", "/account/deletion-request", {"confirm": True}),
    ("POST", "/account/deletion-request/{request_id}/cancel", {}),
    ("POST", "/account/sessions/{session_id}/revoke", {}),
    ("POST", "/auth/logout", {}),
    ("POST", "/auth/mfa/enroll", {}),
    ("POST", "/auth/mfa/confirm", {"code": "000000"}),
    ("POST", "/auth/mfa/verify", {"code": "000000"}),
])
def test_stale_owner_header_cannot_access_or_mutate_new_cookie_account(
    account_factory, account_config, method, path, body,
):
    client = account_factory(config=account_config, mailbox=Mailbox())
    account = login(client, client.app.state.accounts.mail_sender)
    credential = client.cookies.get("math_ege_guest")
    session_id = client.get("/api/v1/account/sessions").json()["sessions"][0]["id"]
    request_id = client.post(
        "/api/v1/account/deletion-request", json={"confirm": True},
    ).json()["request"]["id"]
    response = client.request(
        method, f"/api/v1{path.format(session_id=session_id, request_id=request_id)}",
        json=body, headers={"X-Learning-Owner": str(uuid4())},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "identity_changed"
    assert "set-cookie" not in response.headers
    assert client.cookies.get("math_ege_guest") == credential
    assert client.get("/api/v1/account").json() == account
    assert client.get("/api/v1/account/deletion-request").json()["request"]["id"] == request_id


def test_matching_owner_header_keeps_settings_and_logout_transitions_working(
    account_factory, account_config,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    account = login(client, mailbox)
    headers = {"X-Learning-Owner": account["root_guest_id"]}
    response = client.patch("/api/v1/account", json={"daily_minutes": 30}, headers=headers)
    assert response.status_code == 200
    assert response.json()["daily_minutes"] == 30
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 200
    assert client.get("/api/v1/account").status_code == 401


def test_magic_link_bootstrap_does_not_depend_on_cached_learning_owner(
    account_factory, account_config,
):
    mailbox = Mailbox()
    client = account_factory(config=account_config, mailbox=mailbox)
    client.headers["X-Learning-Owner"] = str(uuid4())
    assert client.get("/api/v1/auth/config").status_code == 200
    account = login(client, mailbox)
    del client.headers["X-Learning-Owner"]
    assert client.get("/api/v1/account").json() == account
