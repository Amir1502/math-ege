"""Read-only queue observations and exact-account impact counts, never erasure authority."""

import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import CheckConstraint, MetaData, Table, func, inspect, or_, select, union
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector

from app.accounts.models import (
    AccessSession,
    Account,
    AccountDeletionCancellation,
    AccountDeletionReceipt,
    AccountDeletionRequest,
    AccountRoleAudit,
    GuestClaim,
    MagicLink,
)
from app.models import Guest
from app.operations.common import OperationError, canonical_uuid, utc

_ACCOUNT_TABLES = (
    "accounts", "guest_claims", "access_sessions", "account_consents",
    "account_deletion_requests", "account_totp_credentials", "account_deletion_cancellations",
)
_GUEST_TABLES = (
    "guests", "learning_sessions", "attempts", "seen_tasks", "idempotency_records", "assessments",
)
_OWNER_TABLES = ("learning_evidence", "learning_policy_states", "learning_annotations")


def _check_sql(value: str) -> str:
    return re.sub(r'[\s"()]|::(?:character varying|text)', "", value.lower())


def _fulfillment_ready(schema: Inspector, names: set[str]) -> bool:
    required = set(_ACCOUNT_TABLES + _GUEST_TABLES + _OWNER_TABLES) | {
        "account_magic_links", "account_role_audit", "account_deletion_receipts",
    }
    if not required <= names:
        return False
    checked = (
        Account, Guest, AccessSession, AccountDeletionRequest, AccountDeletionCancellation,
        AccountDeletionReceipt, AccountRoleAudit, MagicLink,
    )
    for model in checked:
        table = model.__table__
        columns = {column["name"]: column for column in schema.get_columns(table.name)}
        if not set(table.c.keys()) <= columns.keys() or any(
            column.nullable != columns[column.name]["nullable"] for column in table.c
        ):
            return False
        if set(schema.get_pk_constraint(table.name)["constrained_columns"]) != {
            column.name for column in table.primary_key.columns
        }:
            return False
        actual_foreign_keys = {
            (tuple(key["constrained_columns"]), key["referred_table"],
             tuple(key["referred_columns"]))
            for key in schema.get_foreign_keys(table.name)
        }
        expected_foreign_keys = {
            (tuple(key.column_keys), key.referred_table.name,
             tuple(element.column.name for element in key.elements))
            for key in table.foreign_key_constraints
        }
        if not expected_foreign_keys <= actual_foreign_keys:
            return False
        if model is AccountDeletionReceipt and (
            set(columns) != set(table.c.keys()) or actual_foreign_keys
        ):
            return False
        if model in (
            AccountDeletionRequest, AccountDeletionCancellation, AccountDeletionReceipt,
            AccountRoleAudit,
        ):
            actual_checks = {
                _check_sql(check["sqltext"]) for check in schema.get_check_constraints(table.name)
            }
            if not {
                _check_sql(str(check.sqltext)) for check in table.constraints
                if isinstance(check, CheckConstraint)
            } <= actual_checks:
                return False
    for name in required - {model.__tablename__ for model in checked}:
        owner_column = "owner_id" if name in _OWNER_TABLES else (
            "guest_id" if name in _GUEST_TABLES else "account_id"
        )
        if owner_column not in {column["name"] for column in schema.get_columns(name)}:
            return False
    return True


def _capability(schema: Inspector, names: set[str]) -> dict[str, Any]:
    ready = _fulfillment_ready(schema, names)
    return {
        "fulfillment_available": ready,
        "fulfillment_blocker": None if ready else "durable_completion_schema_required",
        "requires_live_administrator_and_recent_mfa": True,
        "restore_replay_available": False,
        "restore_replay_blocker": "independent_completion_scope_mapping_required",
        "guest_cleanup_enabled": False,
    }


def deletion_status(connection: Connection, now: datetime) -> dict[str, Any]:
    now = utc(now)
    schema = inspect(connection)
    names = set(schema.get_table_names())
    table = AccountDeletionRequest.__table__
    requested = table.c.status == "requested"
    pending = connection.scalar(select(func.count()).select_from(table).where(requested))
    overdue = connection.scalar(select(func.count()).select_from(table).where(
        requested, table.c.deadline_at <= now,
    ))
    due_soon = connection.scalar(select(func.count()).select_from(table).where(
        requested, table.c.deadline_at > now, table.c.deadline_at <= now + timedelta(days=7),
    ))
    other = connection.scalar(select(func.count()).select_from(table).where(~requested))
    earliest = connection.scalar(select(func.min(table.c.deadline_at)).where(requested))
    terminal_counts = {
        key: connection.scalar(select(func.count()).select_from(Table(
            name, MetaData(), autoload_with=connection,
        ))) if name in names else None
        for key, name in (
            ("completed_receipt_count", "account_deletion_receipts"),
            ("retained_cancellation_count", "account_deletion_cancellations"),
        )
    }
    return {
        "dry_run": True, "requested_count": pending, "overdue_count": overdue,
        "due_within_seven_days_count": due_soon, "unrecognized_status_count": other,
        "observed_at": now.isoformat(),
        "earliest_pending_deadline_at": utc(earliest).isoformat() if earliest is not None else None,
        "dispatcher_status": "external_configuration_not_observed",
        **terminal_counts, **_capability(schema, names),
    }


def deletion_plan(
    connection: Connection, *, account_id: str, request_id: str, now: datetime,
) -> dict[str, Any]:
    account_id, request_id, now = canonical_uuid(account_id), canonical_uuid(request_id), utc(now)
    account = Account.__table__
    requests, claims = AccountDeletionRequest.__table__, GuestClaim.__table__
    matched = connection.execute(select(
        account.c.root_guest_id, requests.c.requested_at, requests.c.deadline_at, requests.c.status,
    ).join(requests, requests.c.account_id == account.c.id).where(
        account.c.id == account_id, requests.c.id == request_id,
    )).mappings().one_or_none()
    if matched is None or matched["status"] != "requested":
        raise OperationError("account_and_pending_request_scope_mismatch")
    requested, deadline = utc(matched["requested_at"]), utc(matched["deadline_at"])
    if requested > now or deadline != requested + timedelta(days=30):
        raise OperationError("invalid_persisted_deletion_deadline")
    root = canonical_uuid(matched["root_guest_id"])
    origins = select(claims.c.guest_id).where(claims.c.account_id == account_id)
    schema = inspect(connection)
    names = set(schema.get_table_names())
    required = (set(_ACCOUNT_TABLES) - {"account_deletion_cancellations"}) | set(
        _GUEST_TABLES[:5],
    ) | {"account_magic_links"}
    if not required <= names:
        raise OperationError("account_planning_schema_incomplete")
    counts = {}
    metadata = MetaData()
    for name in (*_ACCOUNT_TABLES, *_GUEST_TABLES, *_OWNER_TABLES):
        if name not in names:
            continue
        table = Table(name, metadata, autoload_with=connection)
        if name in _ACCOUNT_TABLES:
            column = table.c.id if name == "accounts" else table.c.account_id
            condition = column == account_id
        else:
            column = table.c.id if name == "guests" else (
                table.c.owner_id if name in _OWNER_TABLES else table.c.guest_id
            )
            condition = or_(column == root, column.in_(origins))
        counts[name] = connection.scalar(select(func.count()).select_from(table).where(condition))
    email = select(account.c.email).where(account.c.id == account_id).scalar_subquery()
    links = Table("account_magic_links", metadata, autoload_with=connection)
    bound_links = links.alias("bound_links")
    associated = or_(bound_links.c.guest_id == root, bound_links.c.guest_id.in_(origins))
    current_associated = or_(links.c.guest_id == root, links.c.guest_id.in_(origins))
    if "credential_account_id" in links.c:
        associated = or_(associated, bound_links.c.credential_account_id == account_id)
        current_associated = or_(current_associated, links.c.credential_account_id == account_id)
    digests = union(
        select(Guest.token_digest).where(or_(Guest.id == root, Guest.id.in_(origins))),
        select(AccessSession.token_digest).where(AccessSession.account_id == account_id),
        select(bound_links.c.browser_credential_digest).where(
            associated, bound_links.c.browser_credential_digest.is_not(None),
        ),
    )
    counts["account_magic_links"] = connection.scalar(select(func.count()).select_from(links).where(
        or_(links.c.email == email, current_associated,
            links.c.browser_credential_digest.in_(digests)),
    ))
    audit_disposition = None
    if "account_role_audit" in names:
        audits = Table("account_role_audit", metadata, autoload_with=connection)
        escaped_email = func.replace(func.replace(func.replace(email, "/", "//"), "%", "/%"),
                                     "_", "/_")
        operator = func.lower(audits.c.operator).contains(escaped_email, escape="/")
        linked = audits.c.account_id == account_id
        audit_disposition = {
            key: connection.scalar(select(func.count()).select_from(audits).where(condition))
            for key, condition in (
                ("linked_subject_count", linked), ("operator_reference_count", operator),
                ("affected_row_count", or_(linked, operator)),
            )
        }
        audit_disposition["rows_deleted"] = 0
    return {
        "dry_run": True, "matched_account_count": 1, "matched_request_count": 1,
        "deadline_reached": deadline <= now, "counts": counts,
        "inventory_scope": "active_cloud_v1", "audit_disposition": audit_disposition,
        **_capability(schema, names),
    }
