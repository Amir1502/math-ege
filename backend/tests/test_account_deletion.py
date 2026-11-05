"""Deletion executes only against newly created, explicitly seeded pytest databases."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Event, local
from uuid import uuid4

import pyotp
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import MetaData, event, func, inspect, null, select
from sqlalchemy.dialects import postgresql

from app.accounts.models import (
    AccessSession,
    Account,
    AccountConsent,
    AccountDeletionCancellation,
    AccountDeletionReceipt,
    AccountDeletionRequest,
    AccountRoleAudit,
    AuthRateLimit,
    GuestClaim,
    MagicLink,
    TotpCredential,
)
from app.accounts.service import AccountService
from app.accounts.tokens import new_token, token_digest
from app.assessments.models import AssessmentRecord
from app.config import Settings
from app.database import Database
from app.editor.models import EditorRevision
from app.editor.repository import published_content
from app.errors import ApiError
from app.learning.models import EvidenceRecord, LearningState, TaskAnnotation
from app.models import (
    AttemptRecord,
    Base,
    Guest,
    IdempotencyRecord,
    LearningSessionRecord,
    SeenTask,
)
from app.services import LearningService
from tests.helpers import answer, draft, start
from tests.test_account_expiry import _advance_after_row_lock, _queued_post
from tests.test_accounts import Mailbox, request_link
from tests.test_editor import act, reviewed
from tests.test_editor import editor as editor


def _snapshot(database):
    with database.transaction() as db:
        return {
            table.name: list(db.execute(
                select(table).order_by(*table.primary_key.columns),
            ).mappings())
            for table in Base.metadata.sorted_tables
        }


def _request(client):
    response = client.post("/api/v1/account/deletion-request", json={"confirm": True})
    assert response.status_code == 200, response.text
    return response.json()["request"]


def _cancel(client, request_id):
    return client.post(f"/api/v1/account/deletion-request/{request_id}/cancel", json={})


def _fulfill(client, request_id, *, confirm=True):
    return client.post(
        f"/api/v1/admin/account-deletions/{request_id}/fulfill", json={"confirm": confirm},
    )


def _receipt(client, request_id):
    return client.get(f"/api/v1/admin/account-deletions/{request_id}/receipt")


def test_cancellation_is_durable_idempotent_and_does_not_authorize_a_later_request(editor, clock):
    client, identity = editor
    request = _request(client)
    before = _snapshot(client.app.state.database)

    canceled = _cancel(client, request["id"])

    assert canceled.status_code == 200, canceled.text
    assert canceled.json() == {
        **request, "status": "canceled", "canceled_at": clock[0].isoformat(),
    }
    assert _cancel(client, request["id"]).json() == canceled.json()
    assert client.get("/api/v1/account/deletion-request").json() == {"request": None}
    after = _snapshot(client.app.state.database)
    for name, rows in before.items():
        if name not in {"account_deletion_requests", "account_deletion_cancellations"}:
            assert after[name] == rows, name

    clock[0] += timedelta(seconds=1)
    replacement = _request(client)
    assert replacement["id"] != request["id"]
    assert replacement["requested_at"] == clock[0].isoformat()
    assert _cancel(client, request["id"]).json() == canceled.json()
    assert client.get("/api/v1/account/deletion-request").json()["request"] == replacement
    identity.use("admin")
    before = _snapshot(client.app.state.database)
    response = _fulfill(client, request["id"])
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "deletion_canceled"
    assert _snapshot(client.app.state.database) == before


@pytest.mark.parametrize("actor", [
    "anonymous", "guest", "forged-id", "student", "author", "reviewer", "admin-no-mfa",
    "stale-mfa", "unconfirmed-mfa", "expired", "revoked",
])
def test_fulfillment_and_receipt_require_a_live_admin_session_with_recent_mfa(editor, clock, actor):
    client, identity = editor
    request = _request(client)
    database = client.app.state.database
    if actor == "anonymous":
        client.cookies.clear()
    elif actor == "guest":
        client.cookies.clear()
        assert client.post("/api/v1/guest", json={}).status_code == 200
    elif actor == "forged-id":
        client.cookies.clear()
        client.cookies.set(client.app.state.settings.cookie_name, identity.actors["admin"].id)
    elif actor == "student":
        with database.transaction(write=True) as db:
            db.get(Account, identity.actors["author"].id).role = "student"
    elif actor in {"author", "reviewer"}:
        identity.use(actor)
    else:
        identity.use("admin")
        with database.transaction(write=True) as db:
            access = db.get(AccessSession, identity.sessions["admin"])
            if actor == "admin-no-mfa":
                access.mfa_verified_at = None
            elif actor == "stale-mfa":
                access.mfa_verified_at = clock[0] - timedelta(minutes=15)
            elif actor == "unconfirmed-mfa":
                db.get(TotpCredential, identity.actors["admin"].id).confirmed_at = None
            elif actor == "revoked":
                access.revoked_at = clock[0]
            else:
                access.expires_at = clock[0]
    before = _snapshot(database)

    for response in (_fulfill(client, request["id"]), _receipt(client, request["id"])):
        assert response.status_code == (401 if actor in {
            "anonymous", "guest", "forged-id", "expired", "revoked",
        } else 403)
    assert _snapshot(database) == before


def test_foreign_cancellation_and_unknown_request_leave_every_record_untouched(editor):
    client, identity = editor
    request = _request(client)
    identity.use("reviewer")
    before = _snapshot(client.app.state.database)
    assert _cancel(client, request["id"]).status_code == 404
    assert _snapshot(client.app.state.database) == before
    identity.use("admin")
    assert _fulfill(client, str(uuid4())).status_code == 404
    assert _fulfill(client, request["id"], confirm=False).status_code == 422
    assert _snapshot(client.app.state.database) == before


def test_fulfillment_removes_account_and_credentials_and_persists_a_non_pii_receipt(editor, clock):
    client, identity = editor
    target = identity.actors["author"]
    credential = identity.credentials["author"]
    request = _request(client)
    identity.use("admin")

    response = _fulfill(client, request["id"])

    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt == {
        "request_id": request["id"], "status": "completed", "scope": "active_cloud_v1",
        "requested_at": request["requested_at"], "deadline_at": request["deadline_at"],
        "completed_at": clock[0].isoformat(),
    }
    assert target.id not in response.text and target.owner_id not in response.text
    assert credential not in response.text and "@" not in response.text
    with client.app.state.database.transaction() as db:
        assert db.get(Account, target.id) is None
        assert db.get(AccessSession, identity.sessions["author"]) is None
        assert db.get(AccountDeletionRequest, request["id"]) is None
    assert _receipt(client, request["id"]).json() == receipt
    before = _snapshot(client.app.state.database)
    assert _fulfill(client, request["id"]).json() == receipt
    assert _snapshot(client.app.state.database) == before
    with pytest.raises(ApiError) as rejected:
        client.app.state.accounts.get_account(credential)
    assert rejected.value.status_code == 401


def _practice(client):
    created = start(client)
    assert created.status_code == 200, created.text
    session = created.json()
    response = answer(client, session, session["tasks"][0], "42")
    assert response.status_code == 200, response.text
    assert draft(client, session, session["tasks"][1], "12,").status_code == 200
    return session


def _seed_learning(db, origin, session, now):
    """Exercise every private store, including all four assessment lifecycle states."""
    for state in ("prepared", "active", "awaiting_snapshot", "completed"):
        assessment_id = str(uuid4())
        db.add(AssessmentRecord(
            id=assessment_id, guest_id=origin, profile_id="isolated-profile",
            profile_revision="original", profile_snapshot={"private": origin},
            tasks_snapshot=[{"private_condition": origin}], mode="exam", status=state,
            created_at=now, started_at=None if state == "prepared" else now,
            deadline_at=None if state == "prepared" else now + timedelta(minutes=60),
            released_at=now if state == "completed" else None,
            duration_minutes=60, writer_device_id=str(uuid4()), writer_generation=2,
            draft_revision=3, current_index=1, drafts={"answer": "12,"},
            first_drafts={"answer": "7"}, answer_context={"private": origin},
            server_result={"private_result": origin} if state in {
                "awaiting_snapshot", "completed",
            } else None,
            local_result={"private_result": origin} if state == "completed" else None,
            finish_hash="f" * 64 if state == "completed" else None,
        ))
    db.add(EvidenceRecord(
        event_id=f"isolated:{uuid4()}", owner_id=origin, session_id=session["id"],
        source="practice", payload={"private_evidence": origin}, created_at=now, recorded_at=now,
    ))
    if db.get(LearningState, origin) is None:
        db.add(LearningState(
            owner_id=origin, algorithm_version="isolated", policy_config={"private": origin},
            notice="private projection", updated_at=now,
        ))
    db.add(TaskAnnotation(
        id=str(uuid4()), owner_id=origin, session_id=session["id"],
        task_id=session["tasks"][0]["id"], source="practice", favourite=True, manual=True,
        not_understood=True, cause="theory", created_at=now, updated_at=now,
    ))


def _link(db, now, *, email, credential=None, guest_id=None, account_id=None):
    link = MagicLink(
        id=str(uuid4()), email=email, token_digest=token_digest(new_token()),
        browser_state_digest=token_digest(new_token()), browser_credential_digest=credential,
        credential_account_id=account_id, guest_id=guest_id, policy_version="isolated-fixture",
        created_at=now, expires_at=now + timedelta(minutes=15), consumed_at=None,
    )
    db.add(link)
    return link.id


@pytest.fixture
def populated(editor, clock):
    client, identity = editor
    database = client.app.state.database
    accounts = client.app.state.accounts
    target, foreign = identity.actors["author"], identity.actors["reviewer"]
    mailbox = Mailbox()
    accounts.mail_sender = mailbox
    sessions = {target.owner_id: _practice(client)}
    stale_tokens = []
    # These are real claims, with original practice IDs and old credential bindings.
    for _ in range(2):
        client.cookies.clear()
        origin = client.post("/api/v1/guest", json={}).json()["id"]
        stale_tokens.append(client.cookies.get("math_ege_guest"))
        sessions[origin] = _practice(client)
        link = request_link(client, mailbox, "author@editor.test", "isolated-fixture")
        claimed = client.post("/api/v1/auth/complete", json={"token": link})
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["id"] == target.id
        stale_tokens.append(client.cookies.get("math_ege_guest"))
    identity.use("reviewer")
    foreign_session = _practice(client)
    identity.use("author")
    # Include private canceled-request history in the final purge.
    canceled_request = _request(client)
    assert _cancel(client, canceled_request["id"]).status_code == 200
    request = _request(client)
    with database.transaction(write=True) as db:
        for origin, session in sessions.items():
            _seed_learning(db, origin, session, clock[0])
        _seed_learning(db, foreign.owner_id, foreign_session, clock[0])
        db.add(AccountConsent(
            id=str(uuid4()), account_id=target.id, policy_version="old-policy",
            accepted_at=clock[0] - timedelta(days=1),
        ))
        db.add(AccountRoleAudit(
            id=str(uuid4()), account_id=target.id, previous_role="student", new_role="methodist",
            operator="Private Person <AUTHOR@EDITOR.TEST>", changed_at=clock[0],
        ))
        db.add(AccountRoleAudit(
            id=str(uuid4()), account_id=foreign.id, previous_role="student", new_role="methodist",
            operator="unrelated-local-operator", changed_at=clock[0],
        ))
        # Email-only, live bearer, historic claimed origin, and post-rotation bindings.
        removed_links = {
            _link(db, clock[0], email="author@editor.test"),
            _link(db, clock[0], email="author@editor.test", guest_id=foreign.owner_id,
                  credential=token_digest(identity.credentials["reviewer"]), account_id=foreign.id),
            _link(db, clock[0], email="alternate@isolated.test",
                  credential=token_digest(identity.credentials["author"])),
            _link(db, clock[0], email="alternate@isolated.test",
                  guest_id=next(origin for origin in sessions if origin != target.owner_id)),
            _link(db, clock[0], email="rotated@isolated.test",
                  credential=token_digest(new_token()), account_id=target.id),
        }
        old_digest = token_digest(new_token())
        db.add(AccessSession(
            id=str(uuid4()), account_id=target.id, token_digest=old_digest,
            created_at=clock[0] - timedelta(days=60), expires_at=clock[0] - timedelta(days=30),
            last_seen_at=clock[0] - timedelta(days=31), revoked_at=clock[0] - timedelta(days=31),
            mfa_verified_at=None,
        ))
        removed_links.add(_link(
            db, clock[0], email="old-session@isolated.test", credential=old_digest,
        ))
        kept_link = _link(
            db, clock[0], email="reviewer@editor.test", guest_id=foreign.owner_id,
            credential=token_digest(identity.credentials["reviewer"]), account_id=foreign.id,
        )
    identity.use("admin")
    return client, identity, request, sessions, stale_tokens, removed_links, kept_link


def _assert_private_scope_absent(database, account_id, origins):
    with database.transaction() as db:
        assert db.get(Account, account_id) is None
        assert not list(db.scalars(select(Guest).where(Guest.id.in_(origins))))
        for model in (
            AccessSession, TotpCredential, AccountConsent, GuestClaim,
            AccountDeletionRequest, AccountDeletionCancellation,
        ):
            assert db.scalar(select(func.count()).select_from(model).where(
                model.account_id == account_id,
            )) == 0, model.__tablename__
        for model in (
            LearningSessionRecord, AttemptRecord, SeenTask, IdempotencyRecord, AssessmentRecord,
        ):
            assert db.scalar(select(func.count()).select_from(model).where(
                model.guest_id.in_(origins),
            )) == 0, model.__tablename__
        for model in (EvidenceRecord, LearningState, TaskAnnotation):
            assert db.scalar(select(func.count()).select_from(model).where(
                model.owner_id.in_(origins),
            )) == 0, model.__tablename__


def test_all_original_origins_and_private_snapshots_are_removed_without_touching_foreign_data(
    populated,
):
    client, identity, request, sessions, stale_tokens, removed_links, kept_link = populated
    database = client.app.state.database
    target, foreign = identity.actors["author"], identity.actors["reviewer"]
    before = _snapshot(database)
    assert len(sessions) == 3
    assert len(before["assessments"]) == 16
    assert all(before[name] for name in (
        "attempts", "seen_tasks", "idempotency_records", "learning_evidence",
        "learning_policy_states", "learning_annotations", "account_deletion_cancellations",
    ))

    response = _fulfill(client, request["id"])

    assert response.status_code == 200, response.text
    _assert_private_scope_absent(database, target.id, list(sessions))
    after = _snapshot(database)
    for name, rows in before.items():
        foreign_rows = [row for row in rows if (
            row.get("guest_id") == foreign.owner_id or row.get("owner_id") == foreign.owner_id
            or row.get("account_id") == foreign.id or row.get("id") in {
                foreign.id, foreign.owner_id, kept_link,
            }
        )]
        for row in foreign_rows:
            if name == "account_magic_links" and row["id"] in removed_links:
                # A foreign browser's link to the deleted email is still in scope.
                assert row not in after[name]
            else:
                assert row in after[name], (name, row)
    assert {row["id"] for row in after["account_magic_links"]} == {kept_link}
    assert removed_links.isdisjoint(row["id"] for row in after["account_magic_links"])
    for credential in [identity.credentials["author"], *stale_tokens]:
        with pytest.raises(ApiError) as rejected:
            client.app.state.service.identity(credential)
        assert rejected.value.status_code == 401
    with database.transaction() as db:
        audit = db.scalars(select(AccountRoleAudit).where(
            AccountRoleAudit.subject_id == target.id,
        )).one()
        assert audit.account_id is None
        assert audit.operator.startswith("deleted-operator:")
        assert (audit.previous_role, audit.new_role) == ("student", "methodist")
    assert "author@editor.test" not in str(after).lower()


@pytest.mark.parametrize("boundary", [
    "DELETE FROM learning_sessions", "INSERT INTO account_deletion_receipts",
])
def test_failed_purge_and_failed_receipt_commit_roll_back_every_change_and_allow_retry(
    populated, boundary,
):
    client, identity, request, sessions, _, _, _ = populated
    database = client.app.state.database
    before = _snapshot(database)
    reached = []

    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith(boundary):
            reached.append(statement)
            raise RuntimeError("isolated simulated storage failure")

    event.listen(database.engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="isolated simulated"):
            client.app.state.accounts.fulfill_deletion(
                identity.credentials["admin"], request["id"], confirm=True,
            )
    finally:
        event.remove(database.engine, "after_cursor_execute", fail)
    assert reached
    assert _snapshot(database) == before
    assert _receipt(client, request["id"]).status_code == 404
    assert _fulfill(client, request["id"]).status_code == 200
    _assert_private_scope_absent(database, identity.actors["author"].id, list(sessions))


@pytest.mark.parametrize("expires", ["mfa", "session"])
@pytest.mark.parametrize("model,occurrence", [
    (AuthRateLimit, 1), (Guest, 1), (Account, 1), (AccountDeletionRequest, 1),
    (AccessSession, 2), (TotpCredential, 2), (MagicLink, 1), (AccountRoleAudit, 1),
], ids=["login-barrier", "roots", "accounts", "request", "sessions", "mfa", "links", "audit"])
def test_fulfillment_rechecks_admin_expiry_after_all_lock_boundaries(
    editor, clock, expires, model, occurrence,
):
    client, identity = editor
    request = _request(client)
    identity.use("admin")
    database = client.app.state.database
    if expires == "session":
        with database.transaction(write=True) as db:
            db.get(AccessSession, identity.sessions["admin"]).expires_at = (
                clock[0] + timedelta(minutes=15)
            )
    before = _snapshot(database)
    clock[0] += timedelta(seconds=899)
    with _advance_after_row_lock(database, clock, model, occurrence):
        response = _fulfill(client, request["id"])
    assert response.status_code == (403 if expires == "mfa" else 401), response.text
    assert response.json()["error"]["code"] == (
        "mfa_required" if expires == "mfa" else "guest_required"
    )
    assert _snapshot(database) == before


@pytest.mark.parametrize("boundary", ["writer", "request", "cancellation"])
def test_cancellation_rechecks_owner_session_after_lock_wait(editor, clock, boundary):
    client, identity = editor
    request = _request(client)
    if boundary == "cancellation":
        assert _cancel(client, request["id"]).status_code == 200
    database = client.app.state.database
    with database.transaction(write=True) as db:
        db.get(AccessSession, identity.sessions["author"]).expires_at = (
            clock[0] + timedelta(seconds=1)
        )
    before = _snapshot(database)
    if boundary == "writer":
        response = _queued_post(
            client, clock, f"/api/v1/account/deletion-request/{request['id']}/cancel", {},
        )
    else:
        model = AccountDeletionRequest if boundary == "request" else AccountDeletionCancellation
        with _advance_after_row_lock(database, clock, model):
            response = _cancel(client, request["id"])
    assert response.status_code == 401, response.text
    assert _snapshot(database) == before


def _compete(database, first, second, *, model=AccountDeletionRequest):
    """Hold the winning request lock, then observe the losing real SQLite writer."""
    ready, waiting, acquired, release = Event(), Event(), Event(), Event()
    worker = local()

    def before(connection, cursor, statement, parameters, context, executemany):
        if getattr(worker, "name", None) == "second" and statement == "BEGIN IMMEDIATE":
            waiting.set()

    def after(connection, cursor, statement, parameters, context, executemany):
        if getattr(worker, "name", None) == "second" and statement == "BEGIN IMMEDIATE":
            acquired.set()
        if (
            getattr(worker, "name", None) == "first" and not ready.is_set()
            and context.compiled is not None and statement.startswith("SELECT ")
            and f"FROM {model.__tablename__}" in statement
            and str(context.compiled.statement.compile(dialect=postgresql.dialect()))
            .endswith("FOR UPDATE")
        ):
            ready.set()
            assert release.wait(timeout=10), "winning transaction was not released"

    def run(name, action):
        worker.name = name
        try:
            return action()
        except ApiError as exc:
            return exc

    event.listen(database.engine, "before_cursor_execute", before)
    event.listen(database.engine, "after_cursor_execute", after)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            winner = pool.submit(run, "first", first)
            try:
                assert ready.wait(timeout=10), "winner did not lock the active request"
                loser = pool.submit(run, "second", second)
                assert waiting.wait(timeout=10), "loser did not reach the writer lock"
                assert not acquired.is_set() and not loser.done()
            finally:
                release.set()
            results = winner.result(timeout=10), loser.result(timeout=10)
            assert acquired.is_set()
            return results
    finally:
        event.remove(database.engine, "before_cursor_execute", before)
        event.remove(database.engine, "after_cursor_execute", after)


@pytest.mark.parametrize("winner", ["cancel", "fulfill", "duplicate-fulfill"])
def test_cancel_and_fulfill_have_one_serialized_winner(editor, winner):
    client, identity = editor
    request = _request(client)
    accounts = client.app.state.accounts

    def cancel():
        return accounts.cancel_deletion(identity.credentials["author"], request["id"])

    def fulfill():
        return accounts.fulfill_deletion(identity.credentials["admin"], request["id"], confirm=True)

    first = cancel if winner == "cancel" else fulfill
    second = cancel if winner == "fulfill" else fulfill
    one, two = _compete(client.app.state.database, first, second)
    assert not isinstance(one, ApiError)
    if winner == "cancel":
        assert one.status == "canceled" and isinstance(two, ApiError)
        assert two.code == "deletion_canceled"
        assert accounts.get_account(identity.credentials["author"]).id == (
            identity.actors["author"].id
        )
    elif winner == "fulfill":
        assert one.status == "completed" and isinstance(two, ApiError)
        assert two.status_code == 401
    else:
        assert one == two and one.status == "completed"
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(AccountDeletionReceipt)) == (
            0 if winner == "cancel" else 1
        )
        assert db.scalar(select(func.count()).select_from(AccountDeletionCancellation)) == (
            1 if winner == "cancel" else 0
        )


@pytest.mark.parametrize("deleted_actor", ["author", "reviewer"])
def test_editor_publication_and_independent_audit_attribution_survive_account_removal(
    editor, content, deleted_actor,
):
    client, identity = editor
    revision = reviewed(client, identity, content)
    identity.use("admin")
    published = act(client, revision, "publish")
    assert published.status_code == 200, published.text
    database = client.app.state.database
    before = _snapshot(database)
    bundle = published_content(database, client.app.state.settings)
    identity.use(deleted_actor)
    request = _request(client)
    identity.use("admin")

    assert _fulfill(client, request["id"]).status_code == 200

    after = _snapshot(database)
    for name, rows in before.items():
        if name.startswith("editor_"):
            assert after[name] == rows, name
    assert published_content(database, client.app.state.settings) == bundle
    assert client.get(f"/api/v1/editor/revisions/{revision['id']}").status_code == 200
    with database.transaction() as db:
        saved = db.get(EditorRevision, revision["id"])
        assert saved.author_id == identity.actors["author"].id
        assert saved.reviewer_id == identity.actors["reviewer"].id
        assert saved.author_id != saved.reviewer_id
        assert saved.status == "published"


def test_pre_rotation_magic_links_are_erased_and_cannot_log_in_after_completion(editor, clock):
    client, identity = editor
    accounts = client.app.state.accounts
    mailbox = Mailbox()
    accounts.mail_sender = mailbox
    old_credential = identity.credentials["author"]
    link_token = request_link(client, mailbox, "alternate@isolated.test", "isolated-fixture")
    browser_state = client.cookies.get("math_ege_auth_state")
    # Use the real enrollment/rotation path on a fresh non-staff account.
    client.cookies.clear()
    login_token = request_link(client, mailbox, "rotation@isolated.test", "isolated-fixture")
    logged_in = client.post("/api/v1/auth/complete", json={"token": login_token})
    assert logged_in.status_code == 200
    original = client.cookies.get("math_ege_guest")
    pending = request_link(client, mailbox, "rotated-alias@isolated.test", "isolated-fixture")
    pending_state = client.cookies.get("math_ege_auth_state")
    enrollment = client.post("/api/v1/auth/mfa/enroll", json={}).json()
    confirmed = client.post("/api/v1/auth/mfa/confirm", json={
        "code": pyotp.TOTP(enrollment["secret"]).at(clock[0]),
    })
    assert confirmed.status_code == 200, confirmed.text
    assert client.cookies.get("math_ege_guest") != original
    request = _request(client)
    identity.use("admin")
    assert _fulfill(client, request["id"]).status_code == 200
    with pytest.raises(ApiError) as rejected:
        accounts.complete(pending, pending_state, original)
    assert rejected.value.code == "invalid_link"
    # A different account's still-valid link has not been removed.
    assert accounts.complete(link_token, browser_state, old_credential)[0].email == (
        "alternate@isolated.test"
    )


def test_populated_v7_upgrade_preserves_legacy_data_and_fulfills_on_the_migrated_schema(
    populated, tmp_path, clock,
):
    client, identity, request, sessions, _, _, _ = populated
    source = _snapshot(client.app.state.database)
    path = tmp_path / "new-deletion-migration.sqlite3"
    assert not path.exists()
    settings = Settings(database_url=f"sqlite:///{path.as_posix()}", environment="test")
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "0007_instance_exposures")
    database = Database(settings)
    try:
        legacy = MetaData()
        legacy.reflect(bind=database.engine)
        with database.transaction(write=True) as db:
            for table in legacy.sorted_tables:
                if table.name not in source or not source[table.name]:
                    continue
                if table.name == "editor_catalog":
                    # Revision 0005 already seeds the empty singleton used here.
                    assert list(db.execute(select(table)).mappings()) == source[table.name]
                    continue
                for row in source[table.name]:
                    # Reflection cannot recover JSON(none_as_null=True). Preserve
                    # SQL NULL explicitly, including unreleased assessment results.
                    db.execute(table.insert().values({
                        key: null() if value is None else value
                        for key, value in row.items() if key in table.c
                    }))

        def original_columns():
            with database.transaction() as db:
                return {
                    table.name: list(db.execute(
                        select(table).order_by(*table.primary_key.columns),
                    ).mappings())
                    for table in legacy.sorted_tables if table.name != "alembic_version"
                }

        before = original_columns()
        command.upgrade(config, "0008_account_deletion_completion")
        assert original_columns() == before
        with database.engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert inspect(database.engine).get_foreign_keys("account_deletion_receipts") == []
        with database.transaction() as db:
            bound = list(db.scalars(select(MagicLink).where(
                MagicLink.browser_credential_digest == token_digest(identity.credentials["author"]),
            )))
            assert bound and all(link.credential_account_id == identity.actors["author"].id
                                 for link in bound)
        upgraded = _snapshot(database)
        with pytest.raises(RuntimeError, match="disabled"):
            command.downgrade(config, "0007_instance_exposures")
        assert _snapshot(database) == upgraded
        accounts = AccountService(LearningService(database, settings, lambda: clock[0]))
        receipt = accounts.fulfill_deletion(
            identity.credentials["admin"], request["id"], confirm=True,
        )
        assert receipt.status == "completed"
        _assert_private_scope_absent(database, identity.actors["author"].id, list(sessions))
        # Recreate the service/engine; completion is a durable fact, not process memory.
        database.dispose()
        database = Database(settings)
        accounts = AccountService(LearningService(database, settings, lambda: clock[0]))
        assert accounts.deletion_receipt(identity.credentials["admin"], request["id"]) == receipt
        assert accounts.fulfill_deletion(
            identity.credentials["admin"], request["id"], confirm=True,
        ) == receipt
    finally:
        database.dispose()


def test_foreign_root_claim_is_rejected_instead_of_erasing_another_account(editor, clock):
    client, identity = editor
    request = _request(client)
    database = client.app.state.database
    with database.transaction(write=True) as db:
        db.add(GuestClaim(
            guest_id=identity.actors["reviewer"].owner_id,
            account_id=identity.actors["author"].id, claimed_at=clock[0],
        ))
    identity.use("admin")
    before = _snapshot(database)
    response = _fulfill(client, request["id"])
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "deletion_scope_changed"
    assert _snapshot(database) == before


def test_unexpected_cross_owner_fk_causes_atomic_failure_not_foreign_cascade(populated, clock):
    client, identity, request, sessions, _, _, _ = populated
    database = client.app.state.database
    session = next(iter(sessions.values()))
    with database.transaction(write=True) as db:
        db.add(AttemptRecord(
            id=str(uuid4()), guest_id=identity.actors["reviewer"].owner_id,
            session_id=session["id"], task_id="foreign-reference", task_revision="original",
            sequence=100, raw_answer="42", normalized_answer="42", correct=False,
            assisted=False, first_attempt=True, independent=True, skipped=False,
            active_seconds=0, created_at=clock[0], checker_revision="isolated",
            expected_answer="0", solution=[],
        ))
    before = _snapshot(database)
    response = _fulfill(client, request["id"])
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "database_unavailable"
    assert _snapshot(database) == before


def test_role_audit_scrubs_deleted_email_in_other_subjects_without_losing_role_history(
    editor, clock,
):
    client, identity = editor
    request = _request(client)
    database = client.app.state.database
    audits = [str(uuid4()) for _ in range(3)]
    with database.transaction(write=True) as db:
        for audit_id, subject, operator in zip(audits, ["author", "reviewer", "author"], [
            "Private Person <AUTHOR@EDITOR.TEST>", "Private Person <AUTHOR@EDITOR.TEST>",
            identity.actors["admin"].id,
        ], strict=True):
            db.add(AccountRoleAudit(
                id=audit_id, account_id=identity.actors[subject].id, previous_role="student",
                new_role="methodist", operator=operator, changed_at=clock[0],
            ))
    identity.use("admin")
    assert _fulfill(client, request["id"]).status_code == 200
    with database.transaction() as db:
        one, two, three = (db.get(AccountRoleAudit, audit_id) for audit_id in audits)
        assert one.account_id is None and one.subject_id == identity.actors["author"].id
        assert two.account_id == identity.actors["reviewer"].id and two.subject_id is None
        assert one.operator == two.operator and one.operator.startswith("deleted-operator:")
        assert three.operator == identity.actors["admin"].id
        assert all(row.changed_at == clock[0] and row.new_role == "methodist"
                   for row in (one, two, three))


def test_re_registration_cannot_be_erased_by_retrying_the_old_request(editor):
    client, identity = editor
    request = _request(client)
    identity.use("admin")
    receipt = _fulfill(client, request["id"])
    assert receipt.status_code == 200
    accounts = client.app.state.accounts
    mailbox = Mailbox()
    accounts.mail_sender = mailbox
    client.cookies.clear()
    link = request_link(client, mailbox, "author@editor.test", "isolated-fixture")
    fresh = client.post("/api/v1/auth/complete", json={"token": link})
    assert fresh.status_code == 200
    assert fresh.json()["id"] != identity.actors["author"].id
    assert fresh.json()["owner_ids"] == [fresh.json()["root_guest_id"]]
    credential = client.cookies.get(client.app.state.settings.cookie_name)
    identity.use("admin")
    assert _fulfill(client, request["id"]).json() == receipt.json()
    assert accounts.get_account(credential).id == fresh.json()["id"]


def test_new_deletion_routes_keep_csrf_strict_bodies_and_private_responses(editor):
    client, identity = editor
    request = _request(client)
    cancel_path = f"/api/v1/account/deletion-request/{request['id']}/cancel"
    assert client.post(cancel_path, json={}, headers={
        "Origin": "https://other.test",
    }).status_code == 403
    assert client.post(cancel_path, json={
        "account_id": identity.actors["reviewer"].id,
    }).status_code == 422
    identity.use("admin")
    fulfill_path = f"/api/v1/admin/account-deletions/{request['id']}/fulfill"
    assert client.post(fulfill_path, json={"confirm": True}, headers={
        "Origin": "https://other.test",
    }).status_code == 403
    assert client.post(fulfill_path, json={
        "confirm": True, "account_id": identity.actors["reviewer"].id,
    }).status_code == 422
    response = _fulfill(client, request["id"])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert _receipt(client, request["id"]).headers["cache-control"] == "no-store"


@pytest.mark.parametrize("winner", ["login", "fulfill"])
def test_concurrent_linking_is_included_in_erasure_or_rejected_without_resurrecting_account(
    editor, winner,
):
    client, identity = editor
    request = _request(client)
    accounts = client.app.state.accounts
    mailbox = Mailbox()
    accounts.mail_sender = mailbox
    client.cookies.clear()
    origin = client.post("/api/v1/guest", json={}).json()["id"]
    credential = client.cookies.get(client.app.state.settings.cookie_name)
    session = _practice(client)
    link = request_link(client, mailbox, "author@editor.test", "isolated-fixture")
    browser_state = client.cookies.get("math_ege_auth_state")

    def complete():
        return accounts.complete(link, browser_state, credential)

    def fulfill():
        return accounts.fulfill_deletion(identity.credentials["admin"], request["id"], confirm=True)

    if winner == "login":
        logged_in, receipt = _compete(accounts.database, complete, fulfill, model=MagicLink)
        assert not isinstance(logged_in, ApiError)
        assert origin in logged_in[0].owner_ids
        assert receipt.status == "completed"
    else:
        receipt, rejected = _compete(accounts.database, fulfill, complete)
        assert receipt.status == "completed"
        assert isinstance(rejected, ApiError) and rejected.code == "invalid_link"
    with accounts.database.transaction() as db:
        assert db.get(Account, identity.actors["author"].id) is None
        assert db.get(GuestClaim, origin) is None
        assert (db.get(Guest, origin) is None) == (winner == "login")
        assert (db.get(LearningSessionRecord, session["id"]) is None) == (winner == "login")


def test_existing_data_rights_sessions_work_when_new_email_login_is_disabled(editor):
    client, identity = editor
    accounts = client.app.state.accounts
    request = _request(client)
    accounts.config = replace(accounts.config, enabled=False)
    assert client.get("/api/v1/auth/config").json()["enabled"] is False
    assert _cancel(client, request["id"]).status_code == 200
    replacement = _request(client)
    assert client.get("/api/v1/account/export").json()["deletion_request"] == replacement
    identity.use("admin")
    assert _fulfill(client, replacement["id"]).status_code == 200
    assert _receipt(client, replacement["id"]).status_code == 200


def test_overdue_fulfillment_keeps_the_original_deadline_and_needs_no_target_session(editor, clock):
    client, identity = editor
    request = _request(client)
    clock[0] += timedelta(days=31)
    identity.use("admin")
    # Explicitly seed a fresh administrator authorization; the target's expired
    # credentials do not withdraw their already-confirmed deletion request.
    with client.app.state.database.transaction(write=True) as db:
        admin = db.get(AccessSession, identity.sessions["admin"])
        admin.expires_at = clock[0] + timedelta(days=1)
        admin.mfa_verified_at = clock[0]
    response = _fulfill(client, request["id"])
    assert response.status_code == 200, response.text
    assert response.json()["deadline_at"] == request["deadline_at"]
    assert response.json()["requested_at"] == request["requested_at"]
    assert response.json()["completed_at"] == clock[0].isoformat()
