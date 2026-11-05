import asyncio
import json
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import Guest
from tests.conftest import MUTATION_HEADERS, TEST_ORIGIN
from tests.helpers import answer, draft, finish, key, start


def test_guest_database_contains_digest_but_never_plain_token(guest_client):
    token = guest_client.cookies.get("math_ege_guest")
    with guest_client.app.state.database.transaction() as db:
        guests = list(db.scalars(select(Guest)))
        assert len(guests) == 1
        assert guests[0].token_digest == sha256(token.encode("ascii")).hexdigest()
        assert token not in vars(guests[0]).values()
        assert len(guests[0].token_digest) == 64


def test_secure_cookie_in_production(tmp_path, content_dir):
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'production.sqlite3').as_posix()}",
        content_dir=content_dir,
        cookie_secure=True,
        allowed_origins=("https://training.example",),
        environment="production",
    )
    app = create_app(settings)
    app.state.database.create_schema_for_tests()
    with TestClient(app, base_url="https://training.example") as client:
        response = client.post(
            "/api/v1/guest", json={},
            headers={"Origin": "https://training.example", "X-Requested-With": "math-ege"},
        )
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert "max-age=" in response.headers["strict-transport-security"]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": TEST_ORIGIN},
        {"X-Requested-With": "math-ege"},
        {"Origin": "null", "X-Requested-With": "math-ege"},
        {"Origin": "https://attacker.example", "X-Requested-With": "math-ege"},
        {"Origin": TEST_ORIGIN + ".attacker.example", "X-Requested-With": "math-ege"},
        {"Origin": TEST_ORIGIN + "/", "X-Requested-With": "math-ege"},
        {"Origin": TEST_ORIGIN, "X-Requested-With": "XMLHttpRequest"},
        {**MUTATION_HEADERS, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_mutation_requires_exact_origin_and_custom_header(client, headers):
    client.headers.clear()
    response = client.post("/api/v1/guest", json={}, headers=headers)
    assert response.status_code == 403
    assert set(response.json()) == {"error"}
    assert set(response.json()["error"]) == {"code", "message", "field"}
    assert "set-cookie" not in response.headers


def test_duplicate_origin_headers_are_rejected(client):
    client.headers.clear()
    response = client.post(
        "/api/v1/guest", json={},
        headers=[("Origin", TEST_ORIGIN), ("Origin", "https://attacker.example"),
                 ("X-Requested-With", "math-ege")],
    )
    assert response.status_code == 403


def test_no_cross_origin_preflight_permission(client):
    response = client.options(
        "/api/v1/guest", headers={"Origin": "https://attacker.example",
                                 "Access-Control-Request-Method": "POST"}
    )
    assert response.status_code == 405
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.parametrize(
    "path", ["/api/v1/progress", "/api/v1/export", f"/api/v1/sessions/{uuid4()}"]
)
def test_private_reads_require_guest_cookie(client, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "guest_required"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("cookie", ["invalid", "a" * 43, "a" * 200, "../etc/passwd"])
def test_invalid_or_unknown_cookie_cannot_access_private_data(client, cookie):
    client.cookies.set("math_ege_guest", cookie)
    assert client.get("/api/v1/progress").status_code == 401
    assert start(client).status_code == 401


def test_unknown_cookie_is_replaced_instead_of_used_for_session_fixation(client):
    forged = "a" * 43
    client.cookies.set("math_ege_guest", forged, domain="testserver.local", path="/")
    response = client.post("/api/v1/guest", json={})
    assert response.status_code == 200
    assert client.cookies.get("math_ege_guest") != forged


def test_guest_expiration_is_enforced_and_does_not_silently_transfer_history(guest_client, clock):
    session = start(guest_client).json()
    old_cookie = guest_client.cookies.get("math_ege_guest")
    clock[0] += timedelta(days=180)
    assert guest_client.get(f"/api/v1/sessions/{session['id']}").status_code == 401
    assert guest_client.post("/api/v1/guest", json={}).status_code == 200
    assert guest_client.cookies.get("math_ege_guest") != old_cookie
    assert guest_client.get("/api/v1/export").json()["sessions"] == []
    assert guest_client.get(f"/api/v1/sessions/{session['id']}").status_code == 404


def test_every_private_session_mutation_checks_owner(client_factory):
    owner = client_factory()
    stranger = client_factory(database_url=owner.app.state.settings.database_url)
    for client in (owner, stranger):
        assert client.post("/api/v1/guest", json={}).status_code == 200
    session = start(owner).json()
    task = session["tasks"][0]
    foreign = stranger.get(f"/api/v1/sessions/{session['id']}")
    missing = stranger.get(f"/api/v1/sessions/{uuid4()}")
    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content
    responses = [
        draft(stranger, session, task, "1"),
        answer(stranger, session, task, "1"),
        finish(stranger, session),
        stranger.post(
            f"/api/v1/sessions/{session['id']}/hints", json={"task_id": task["id"], "level": 1}
        ),
        stranger.post(f"/api/v1/sessions/{session['id']}/solution", json={"task_id": task["id"]}),
    ]
    assert all(response.status_code == 404 for response in responses)
    assert stranger.get("/api/v1/export").json()["sessions"] == []
    assert stranger.get("/api/v1/progress").json()["recent_sessions"] == []
    assert owner.get(f"/api/v1/sessions/{session['id']}").json() == session


def test_task_id_must_belong_to_the_owned_session(guest_client):
    one = start(guest_client, slots=[1]).json()
    other = start(guest_client, slots=[2]).json()["tasks"][0]
    for response in (
        answer(guest_client, one, other, "1"),
        draft(guest_client, one, other, "1"),
        guest_client.post(
            f"/api/v1/sessions/{one['id']}/hints", json={"task_id": other["id"], "level": 1}
        ),
        guest_client.post(f"/api/v1/sessions/{one['id']}/solution", json={"task_id": other["id"]}),
    ):
        assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"slots": [1, 1], "length": 5, "mode": "practice"},
        {"slots": [999], "length": 5, "mode": "practice"},
        {"slots": [1], "length": 13, "mode": "practice"},
        {"slots": [1], "length": 5.0, "mode": "practice"},
        {"slots": [], "length": 5, "mode": "practice"},
        {"slots": [True], "length": 5, "mode": "practice"},
        {"slots": ["1"], "length": 5, "mode": "practice"},
        {"slots": [1], "length": 5, "mode": "exam"},
        {"slots": [1], "length": 5, "mode": "practice", "guest_id": str(uuid4())},
        {"slots": [1], "length": 5, "mode": "practice", "allow_demo_content": True},
    ],
)
def test_session_request_schema_is_closed_and_strict(guest_client, body):
    response = guest_client.post("/api/v1/sessions", json=body, headers=key())
    assert response.status_code == 422
    assert guest_client.get("/api/v1/export").json()["sessions"] == []


@pytest.mark.parametrize(
    "overrides",
    [{"answer": 0}, {"answer": None}, {"answer": "9" * 65}, {"active_seconds": True},
     {"active_seconds": -1}, {"active_seconds": 86401}, {"active_seconds": 1.5},
     {"skipped": "false"}, {"assisted": False}, {"independent": True}, {"correct": True}],
)
def test_attempt_request_rejects_server_owned_flags_and_invalid_values(guest_client, overrides):
    session = start(guest_client).json()
    body = {
        "task_id": session["tasks"][0]["id"], "answer": "0", "active_seconds": 1, "skipped": False
    }
    response = guest_client.post(
        f"/api/v1/sessions/{session['id']}/attempts", json={**body, **overrides}, headers=key()
    )
    assert response.status_code == 422
    assert guest_client.get(f"/api/v1/sessions/{session['id']}").json()["attempts"] == []


@pytest.mark.parametrize("level", [True, 1.0, "1", 0, 4])
def test_hint_level_is_strict_and_bounded(guest_client, level):
    session = start(guest_client).json()
    response = guest_client.post(
        f"/api/v1/sessions/{session['id']}/hints",
        json={"task_id": session["tasks"][0]["id"], "level": level},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("value", [None, "bad", "0" * 36, "{" + str(uuid4()) + "}", uuid4().hex])
def test_idempotency_key_is_required_and_must_be_a_uuid(guest_client, value):
    headers = {} if value is None else {"Idempotency-Key": value}
    response = guest_client.post(
        "/api/v1/sessions", json={"slots": [1], "length": 5, "mode": "practice"}, headers=headers
    )
    assert response.status_code == 422


def test_malformed_json_has_consistent_error_without_echoing_raw_body(client):
    response = client.post(
        "/api/v1/guest", content='{"private-input":', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert "private-input" not in response.text
    assert set(response.json()["error"]) == {"code", "message", "field"}


def test_non_json_mutation_is_rejected(client):
    response = client.post("/api/v1/guest", content="{}", headers={"Content-Type": "text/plain"})
    assert response.status_code == 415


def test_declared_and_streamed_request_bodies_are_bounded(client):
    limit = client.app.state.settings.max_request_bytes
    response = client.post("/api/v1/guest", json={"oversized": "x" * limit})
    assert response.status_code == 413
    streamed = client.post(
        "/api/v1/guest", content=iter([b"x" * (limit // 2), b"x" * limit]),
        headers={"Content-Type": "application/json"},
    )
    assert streamed.status_code == 413
    assert "set-cookie" not in streamed.headers


@pytest.mark.parametrize("content_length", ["-1", "invalid", "9" * 5000])
def test_malformed_content_length_does_not_crash_application(client, content_length):
    response = client.post(
        "/api/v1/guest", content="{}",
        headers={"Content-Type": "application/json", "Content-Length": content_length},
    )
    assert response.status_code in (400, 413)


def test_content_length_with_many_leading_zeroes_remains_valid(client):
    response = client.post(
        "/api/v1/guest", content="{}",
        headers={"Content-Type": "application/json", "Content-Length": "0" * 5000 + "2"},
    )
    assert response.status_code == 200


def test_chunked_body_limit_is_enforced_before_endpoint_execution(client):
    """Exercise ASGI chunk boundaries instead of TestClient's buffered stream."""
    limit = client.app.state.settings.max_request_bytes
    chunks = [b" " * 8000, b" " * 8000, b" " * 8000]

    async def call():
        events = []
        messages = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]

        async def receive():
            return messages.pop(0) if messages else {"type": "http.disconnect"}

        async def send(message):
            events.append(message)

        await client.app(
            {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
             "method": "POST", "scheme": "http", "path": "/api/v1/guest",
             "raw_path": b"/api/v1/guest", "query_string": b"", "root_path": "",
             "headers": [(b"origin", TEST_ORIGIN.encode()), (b"x-requested-with", b"math-ege"),
                         (b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1234), "server": ("testserver", 80)},
            receive, send,
        )
        return events

    assert sum(map(len, chunks)) > limit
    events = asyncio.run(call())
    assert events[0]["status"] == 413
    payload = json.loads(events[1]["body"])
    assert payload["error"]["code"] == "request_too_large"
