import json
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, MetaData, select

from app.accounts.models import (
    AccessSession,
    Account,
    AccountDeletionCancellation,
    AccountDeletionReceipt,
    AccountDeletionRequest,
    AccountRoleAudit,
    MagicLink,
)
from app.config import Settings
from app.database import Database
from app.models import Base, Guest
from app.operations.common import OperationError
from app.operations.rights import deletion_plan, deletion_status
from tests.test_operations import NOW
from tests.test_operations import rights_database as rights_database


@pytest.mark.parametrize("revision,available", [
    ("0007_instance_exposures", False), ("head", True),
])
def test_data_rights_capability_uses_actual_migrated_schema(tmp_path, revision, available):
    backend = Path(__file__).resolve().parents[1]
    database = Database(Settings(database_url=f"sqlite:///{(tmp_path / 'schema.db').as_posix()}"))
    migration = Config(str(backend / "alembic.ini"))
    migration.set_main_option("script_location", str(backend / "migrations"))
    try:
        with database.engine.begin() as connection:
            migration.attributes["connection"] = connection
            command.upgrade(migration, revision)
        with database.engine.connect() as connection:
            status = deletion_status(connection, NOW)
        assert status["fulfillment_available"] is available
        assert status["fulfillment_blocker"] == (
            None if available else "durable_completion_schema_required"
        )
        assert status["restore_replay_available"] is False
        assert status["guest_cleanup_enabled"] is False
    finally:
        database.dispose()


@pytest.mark.parametrize("mismatch", ["receipt_nullability", "receipt_check", "audit_check"])
def test_partial_terminal_schema_does_not_advertise_fulfillment(tmp_path, mismatch):
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        clone = table.to_metadata(metadata)
        if clone.name == "account_deletion_receipts":
            if mismatch == "receipt_nullability":
                clone.c.completed_at.nullable = True
            elif mismatch == "receipt_check":
                clone.constraints = {
                    constraint for constraint in clone.constraints
                    if not isinstance(constraint, CheckConstraint)
                }
        elif clone.name == "account_role_audit" and mismatch == "audit_check":
            clone.constraints = {
                constraint for constraint in clone.constraints
                if not isinstance(constraint, CheckConstraint)
            }
    database = Database(Settings(database_url=f"sqlite:///{(tmp_path / 'partial.db').as_posix()}"))
    try:
        metadata.create_all(database.engine)
        with database.engine.connect() as connection:
            assert deletion_status(connection, NOW)["fulfillment_available"] is False
    finally:
        database.dispose()


def test_status_observes_terminal_counts_and_deadlines_without_dispatch(rights_database):
    database, accounts, requests = rights_database
    with database.transaction(write=True) as db:
        db.add(AccountDeletionCancellation(
            id=str(uuid4()), account_id=accounts[0], requested_at=NOW - timedelta(days=2),
            deadline_at=NOW + timedelta(days=28), canceled_at=NOW - timedelta(days=1),
        ))
        db.add(AccountDeletionReceipt(
            request_id=str(uuid4()), requested_at=NOW - timedelta(days=2),
            deadline_at=NOW + timedelta(days=28), completed_at=NOW - timedelta(days=1),
            scope="active_cloud_v1",
        ))
    with database.engine.connect() as connection:
        status = deletion_status(connection, NOW)
        plan = deletion_plan(connection, account_id=accounts[0], request_id=requests[0], now=NOW)
        assert connection.scalar(select(AccountDeletionRequest.id).where(
            AccountDeletionRequest.id == requests[0],
        )) == requests[0]
    assert status["observed_at"] == NOW.isoformat()
    assert status["earliest_pending_deadline_at"] == (NOW - timedelta(days=1)).isoformat()
    assert status["requested_count"] == 2
    assert status["completed_receipt_count"] == 1
    assert status["retained_cancellation_count"] == 1
    assert status["dispatcher_status"] == "external_configuration_not_observed"
    assert status["requires_live_administrator_and_recent_mfa"] is True
    assert plan["counts"]["account_deletion_cancellations"] == 1
    assert plan["restore_replay_available"] is False
    serialized = json.dumps(status) + json.dumps(plan)
    assert not any(identifier in serialized for identifier in [*accounts, *requests])
    assert "private-" not in serialized


def test_plan_counts_current_and_historical_credential_link_associations(rights_database):
    database, accounts, requests = rights_database
    with database.transaction(write=True) as db:
        root = db.get(Account, accounts[0]).root_guest_id
        digest = db.get(Guest, root).token_digest
        db.add(AccessSession(
            id=str(uuid4()), account_id=accounts[0], token_digest="a" * 64,
            created_at=NOW, expires_at=NOW + timedelta(days=1), last_seen_at=NOW,
            revoked_at=None, mfa_verified_at=None,
        ))
        bindings = [
            (accounts[0], "b" * 64), (None, "b" * 64),
            (None, digest), (None, "a" * 64), (None, "c" * 64),
        ]
        for index, (account_id, bearer_digest) in enumerate(bindings):
            db.add(MagicLink(
                id=str(uuid4()), email=f"unrelated-{index}@example.invalid",
                token_digest=f"{index + 10:064x}", browser_state_digest="d" * 64,
                browser_credential_digest=bearer_digest, credential_account_id=account_id,
                guest_id=None, policy_version="test-1", created_at=NOW,
                expires_at=NOW + timedelta(minutes=15), consumed_at=None,
            ))
    with database.engine.connect() as connection:
        plan = deletion_plan(connection, account_id=accounts[0], request_id=requests[0], now=NOW)
    assert plan["counts"]["account_magic_links"] == 5
    assert "bearer" not in json.dumps(plan)


@pytest.mark.parametrize("email,near_match", [
    ("erase%person@example.invalid", "erase-any-person@example.invalid"),
    ("erase_person@example.invalid", "eraseXperson@example.invalid"),
    ("erase/%_person@example.invalid", "erase/XXperson@example.invalid"),
])
def test_audit_inventory_preserves_literal_email_wildcards(rights_database, email, near_match):
    database, accounts, requests = rights_database
    with database.transaction(write=True) as db:
        db.get(Account, accounts[0]).email = email
        for account_id, operator in [
            (accounts[0], str(uuid4())),
            (accounts[1], "approved by " + email.upper()),
            (accounts[1], "approved by " + near_match),
            (accounts[1], str(uuid4())),
        ]:
            db.add(AccountRoleAudit(
                id=str(uuid4()), account_id=account_id, subject_id=None,
                previous_role="student", new_role="student", operator=operator, changed_at=NOW,
            ))
    with database.engine.connect() as connection:
        plan = deletion_plan(connection, account_id=accounts[0], request_id=requests[0], now=NOW)
    assert plan["audit_disposition"] == {
        "linked_subject_count": 1, "operator_reference_count": 1,
        "affected_row_count": 2, "rows_deleted": 0,
    }
    assert email not in json.dumps(plan)
    assert near_match not in json.dumps(plan)


def test_plan_matches_executor_exact_thirty_day_deadline(rights_database):
    database, accounts, requests = rights_database
    with database.transaction(write=True) as db:
        request = db.get(AccountDeletionRequest, requests[0])
        request.deadline_at = request.requested_at + timedelta(days=29)
    with database.engine.connect() as connection, pytest.raises(
        OperationError, match="invalid_persisted_deletion_deadline",
    ):
        deletion_plan(connection, account_id=accounts[0], request_id=requests[0], now=NOW)
