"""Populated additive migrations and opt-in, non-destructive PostgreSQL recovery.

SQLite verifies the same ORM fixture locally. Only the explicitly enabled
PostgreSQL parameter runs pg_dump/pg_restore; it retains both databases and files.
"""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from alembic import command
from sqlalchemy import JSON, MetaData, Table, inspect, select, text
from sqlalchemy.orm import registry

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
from app.assessments.models import AssessmentRecord
from app.config import Settings
from app.database import Database
from app.editor.models import (
    CorrectionExclusion,
    EditorAudit,
    EditorCatalog,
    EditorPublication,
    EditorRevision,
    TemplateCheckRun,
    TemplateHumanReview,
)
from app.learning.models import EvidenceRecord, LearningState, TaskAnnotation
from app.models import LearningSessionRecord, SeenTask
from app.operations.backup import create_backup, export_inventory, read_bundle, restore_backup
from app.operations.common import OperationError, json_bytes, write_new_json
from app.operations.load import LoadConfig
from app.operations.postgres import PostgresTools

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
BACKEND = Path(__file__).resolve().parents[1]
LEGACY_TABLES = ("guests", "learning_sessions", "attempts", "seen_tasks", "idempotency_records")
MODERN_TABLES = {
    "accounts", "guest_claims", "access_sessions", "account_magic_links", "account_rate_limits",
    "account_consents", "account_deletion_requests", "account_totp_credentials",
    "account_deletion_cancellations", "account_deletion_receipts",
    "account_role_audit", "assessments", "editor_revisions", "editor_catalog",
    "editor_publications", "editor_audit", "editor_exclusions", "editor_template_checks",
    "editor_template_reviews", "learning_evidence", "learning_policy_states",
    "learning_annotations",
}


@pytest.fixture(scope="module")
def gate():
    path = BACKEND.parent / "scripts" / "ops" / "verify_postgres.py"
    spec = importlib.util.spec_from_file_location("postgres_gate_for_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def _tables(database, names):
    metadata = MetaData()
    with database.engine.connect() as connection:
        return {name: Table(name, metadata, autoload_with=connection) for name in sorted(names)}


def _snapshot(database, tables):
    with database.engine.connect() as connection:
        return {
            name: [dict(row) for row in connection.execute(
                select(table).order_by(*table.primary_key),
            ).mappings()]
            for name, table in tables.items()
        }


def _json_value(value):
    if isinstance(value, datetime):
        # Reflected SQLite datetimes are naive; the fixture stores UTC exclusively.
        return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else (
            value.astimezone(UTC).isoformat()
        )
    if isinstance(value, dict):
        return {key: _json_value(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(child) for child in value]
    return value


def _fingerprints(snapshot, tables):
    """Reports contain column names, counts and hashes, never stored row values."""
    return {
        name: {
            "rows": len(rows), "columns": list(tables[name].columns.keys()),
            "original_ids_sha256": _digest([
                [row[column.name] for column in tables[name].primary_key] for row in rows
            ]),
            "all_columns_and_snapshots_sha256": _digest(_json_value(rows)),
        }
        for name, rows in snapshot.items()
    }


def _seed_initial_orm(database, tables):
    """Map the actual 0001 schema, without referencing later mapped columns."""
    mapper = registry()
    mapped = {}
    for name, table in tables.items():
        if name == "learning_sessions":
            table.c.summary_snapshot.type = JSON(none_as_null=True)
        model = type("Initial_" + name, (), {})
        mapper.map_imperatively(model, table)
        mapped[name] = model
    ids = {name: str(uuid4()) for name in ("owner", "reviewer", "completed", "active")}
    ids["attempts"] = [str(uuid4()) for _ in range(5)]
    ids["seen"] = [str(uuid4()) for _ in range(6)]
    ids["idempotency"] = [str(uuid4()) for _ in range(2)]
    tasks = [
        {"id": f"frozen-task-{index}", "revision": "historic-1", "answer": "2,5",
         "statement": "Исходное условие: 5/2.", "solution": ["5/2 = 2,5."],
         "hints": ["Дробь", "Деление", "Десятичная запись"],
         "generation": {"template_id": "historic-template", "seed": 2**32 - index}}
        for index in range(1, 6)
    ]
    try:
        with database.transaction(write=True) as db:
            for role in ("owner", "reviewer"):
                db.add(mapped["guests"](
                    id=ids[role], token_digest=_digest(["synthetic-guest", role]), created_at=NOW,
                    expires_at=NOW + timedelta(days=180), last_seen_at=NOW + timedelta(minutes=1),
                ))
            db.flush()
            for state, owner in (("completed", "owner"), ("active", "reviewer")):
                completed = state == "completed"
                db.add(mapped["learning_sessions"](
                    id=ids[state], guest_id=ids[owner], profile_id="historic-profile",
                    profile_revision="historic-profile-1",
                    profile_snapshot={"revision": "historic-profile-1", "slots": [
                        {"id": "original-slot", "skills": [{"id": "original-skill"}]},
                    ]}, mode="practice", status=state, created_at=NOW,
                    completed_at=NOW + timedelta(minutes=5) if completed else None,
                    current_index=5 if completed else 1, requested_length=5,
                    notice="Сохраняемый текст\nс новой строкой", draft_revision=7,
                    tasks_snapshot=tasks,
                    drafts={"frozen-task-1": {"answer": "2.50", "active_seconds": 17}},
                    help_state={"frozen-task-2": {"hints": 1, "solution": False}},
                    active_seconds={task["id"]: 17 for task in tasks},
                    summary_snapshot={
                        "independent_total": 3, "independent_correct": 3,
                        "task_ids": [task["id"] for task in tasks],
                    } if completed else None,
                ))
            db.flush()
            for index, task in enumerate(tasks):
                assisted, skipped = index == 3, index == 4
                db.add(mapped["attempts"](
                    id=ids["attempts"][index], guest_id=ids["owner"], session_id=ids["completed"],
                    task_id=task["id"], task_revision=task["revision"], sequence=index + 1,
                    raw_answer="" if skipped else "2.50",
                    normalized_answer=None if skipped else "2,5",
                    correct=not skipped, assisted=assisted, first_attempt=True,
                    independent=not (assisted or skipped), skipped=skipped, active_seconds=17,
                    created_at=NOW + timedelta(seconds=index),
                    checker_revision="historic-checker-1",
                    expected_answer="2,5", solution=task["solution"],
                ))
                db.add(mapped["seen_tasks"](
                    id=ids["seen"][index], guest_id=ids["owner"], task_id=task["id"],
                    first_seen_at=NOW, last_seen_at=NOW + timedelta(minutes=5),
                    assistance_seen=assisted, reference_seen=index == 2,
                ))
            db.add(mapped["seen_tasks"](
                id=ids["seen"][5], guest_id=ids["reviewer"], task_id=tasks[0]["id"],
                first_seen_at=NOW, last_seen_at=NOW, assistance_seen=False, reference_seen=True,
            ))
            for index, status in enumerate((200, 409)):
                response = {"session_id": ids["completed"], "frozen": {"value": "2,50"}} if (
                    status == 200
                ) else {"error": {"code": "draft_conflict", "message": "Сохранённый отказ"}}
                db.add(mapped["idempotency_records"](
                    id=ids["idempotency"][index], guest_id=ids["owner"], request_key=str(uuid4()),
                    request_hash=_digest(["original-request", index]),
                    operation="historic-operation",
                    status_code=status, response_json=json.dumps(response, ensure_ascii=False),
                    created_at=NOW,
                ))
    finally:
        mapper.dispose()
    return ids, tasks


def _seed_modern_orm(database, ids, tasks):
    """Storage fixtures exercise every currently known subsystem table and FK."""
    student, reviewer, access, assessment = (str(uuid4()) for _ in range(4))
    revisions = {kind: str(uuid4()) for kind in ("profile", "task", "lesson", "template")}
    with database.transaction(write=True) as db:
        for account, owner, role in (
            (student, ids["owner"], "student"), (reviewer, ids["reviewer"], "methodist"),
        ):
            db.add(Account(
                id=account, email=role + "-recovery@example.invalid", root_guest_id=owner,
                role=role, created_at=NOW, email_verified_at=NOW, policy_version="fixture-1",
                consented_at=NOW, daily_minutes=20,
            ))
        db.flush()
        for account, owner in ((student, ids["owner"]), (reviewer, ids["reviewer"])):
            db.add(GuestClaim(guest_id=owner, account_id=account, claimed_at=NOW))
            db.add(AccountConsent(
                id=str(uuid4()), account_id=account, policy_version="fixture-1", accepted_at=NOW,
            ))
        db.add(AccessSession(
            id=access, account_id=reviewer, token_digest=_digest("synthetic-access"),
            created_at=NOW, expires_at=NOW + timedelta(days=30), last_seen_at=NOW,
            revoked_at=None, mfa_verified_at=NOW,
        ))
        db.add(MagicLink(
            id=str(uuid4()), email="student-recovery@example.invalid", guest_id=ids["owner"],
            token_digest=_digest("synthetic-link"), browser_state_digest=_digest("browser-state"),
            browser_credential_digest=_digest("browser-credential"), credential_account_id=student,
            policy_version="fixture-1",
            created_at=NOW, expires_at=NOW + timedelta(minutes=15), consumed_at=NOW,
        ))
        db.add(AuthRateLimit(key=_digest("synthetic-rate-limit"), events=[1.25, 2.5]))
        db.add(AccountRoleAudit(
            id=str(uuid4()), account_id=reviewer, previous_role="student", new_role="methodist",
            operator="synthetic-verification", changed_at=NOW,
        ))
        db.add(AccountRoleAudit(
            id=str(uuid4()), account_id=None, subject_id=str(uuid4()), previous_role="methodist",
            new_role="student", operator="synthetic-detached-subject", changed_at=NOW,
        ))
        db.add(AccountDeletionRequest(
            id=str(uuid4()), account_id=student, requested_at=NOW,
            deadline_at=NOW + timedelta(days=30), status="requested",
        ))
        db.add(AccountDeletionCancellation(
            id=str(uuid4()), account_id=reviewer, requested_at=NOW - timedelta(days=2),
            deadline_at=NOW + timedelta(days=28), canceled_at=NOW - timedelta(days=1),
        ))
        db.add(AccountDeletionReceipt(
            request_id=str(uuid4()), requested_at=NOW - timedelta(days=30), deadline_at=NOW,
            completed_at=NOW, scope="active_cloud_v1",
        ))
        db.flush()
        db.add(TotpCredential(
            account_id=reviewer, secret_ciphertext="synthetic-storage-ciphertext-not-a-key",
            enrollment_session_id=access, enrollment_expires_at=NOW + timedelta(minutes=10),
            confirmed_at=NOW, last_timecode=123456, attempts=[1.5],
        ))
        for index, status in enumerate(("completed", "awaiting_snapshot")):
            db.add(AssessmentRecord(
                id=assessment if index == 0 else str(uuid4()), guest_id=ids["owner"],
                profile_id="historic-profile", profile_revision="exam-profile-2",
                profile_snapshot={"revision": "exam-profile-2", "independent_of_practice": True},
                tasks_snapshot=tasks, mode="exam", status=status, created_at=NOW, started_at=NOW,
                deadline_at=NOW + timedelta(minutes=60),
                released_at=NOW + timedelta(minutes=60) if index == 0 else None,
                duration_minutes=60, writer_device_id=str(uuid4()), writer_generation=2,
                draft_revision=3, current_index=4, drafts={"frozen-task-1": {"answer": "2.50"}},
                first_drafts={"frozen-task-1": {"answer": "2.60"}},
                answer_context={"frozen-task-1": {"assisted": True}},
                server_result={"score": 4, "answers": ["2,5"], "revision": "server-frozen-1"},
                local_result={"score": 2, "answers": ["2,6"], "revision": "local-frozen-1"}
                if index == 0 else None, finish_hash=_digest("finish") if index == 0 else None,
            ))
        for kind, revision_id in revisions.items():
            payload = {"id": "historic-" + kind, "revision": "1", "snapshot": tasks[0]}
            db.add(EditorRevision(
                id=revision_id, kind=kind, content_id="historic-" + kind, version=1, revision=2,
                status="published", title="Синтетическая редакция для восстановления",
                payload=payload, payload_hash=_digest(payload), base_snapshot=None, parent_id=None,
                author_id=student, reviewer_id=reviewer, change_note="Storage fixture only",
                review_note="Synthetic review record, not content acceptance",
                reviewed_formula=True, reviewed_constraints=True, created_at=NOW, updated_at=NOW,
                reviewed_at=NOW, published_at=NOW,
            ))
        db.flush()
        catalog = db.get(EditorCatalog, 1)
        assert catalog is not None and catalog.revision == 0
        catalog.revision, catalog.profile_revision_id = 4, revisions["profile"]
        parent = db.get(EditorRevision, revisions["task"])
        db.add(EditorRevision(
            id=str(uuid4()), kind="task", content_id="historic-task", version=2, revision=1,
            status="draft", title="Новая редакция не меняет старую", payload={"answer": "3"},
            payload_hash=_digest({"answer": "3"}), base_snapshot=parent.payload,
            parent_id=parent.id, author_id=student, change_note="Frozen parent retained",
            created_at=NOW, updated_at=NOW,
        ))
        for kind, revision_id in revisions.items():
            db.add(EditorPublication(
                kind=kind, content_id="historic-" + kind, revision_id=revision_id, withdrawn=False,
                reason=None, updated_at=NOW,
            ))
        db.add(EditorPublication(
            kind="task", content_id="withdrawn-task", revision_id=None, withdrawn=True,
            reason="Synthetic withdrawal", updated_at=NOW,
        ))
        db.add(EditorAudit(
            id=str(uuid4()), revision_id=revisions["task"], kind="task", content_id="historic-task",
            actor_id=reviewer, actor_role="methodist", action="publish", from_status="ready",
            to_status="published", note="Synthetic publication audit", created_at=NOW,
        ))
        db.add(CorrectionExclusion(
            id=str(uuid4()), task_id="frozen-task-2", task_revision="historic-1",
            reason="Projection only; source history retained", actor_id=reviewer, created_at=NOW,
        ))
        db.add(TemplateCheckRun(
            id=str(uuid4()), revision_id=revisions["template"], payload_hash=_digest("template"),
            profile_hash=_digest("profile"), generator_version="storage-fixture-1",
            checked_revision=2, seed_count=2, output_hashes={"0": _digest(tasks[0])},
            checks=["synthetic-storage-record"], passed=False,
            failure="fixture-not-a-generator-run",
            actor_id=student, created_at=NOW,
        ))
        db.add(TemplateHumanReview(
            id=str(uuid4()), revision_id=revisions["template"], payload_hash=_digest("template"),
            profile_hash=_digest("profile"), seed=2**32 - 1, output_hash=_digest(tasks[0]),
            output_snapshot=tasks[0], approved=False, reviewer_id=reviewer,
            note="Synthetic storage record, no approval claimed", created_at=NOW,
        ))
        db.add(LearningState(
            owner_id=ids["owner"], algorithm_version="fixture-policy-1",
            policy_config={"weights": {"independent": 1.0, "assisted": 0.25}, "window": 30},
            notice="История сохранена", updated_at=NOW,
        ))
        for source, session_id in (("practice", ids["completed"]), ("assessment", assessment)):
            db.add(EvidenceRecord(
                event_id=source + ":" + str(uuid4()), owner_id=ids["owner"], session_id=session_id,
                source=source, payload={"task_id": tasks[0]["id"], "revision": "historic-1",
                                        "attempt_id": ids["attempts"][0], "independent": False},
                created_at=NOW, recorded_at=NOW + timedelta(seconds=1),
            ))
            db.add(TaskAnnotation(
                id=str(uuid4()), owner_id=ids["owner"], session_id=session_id,
                task_id=tasks[0]["id"],
                source=source, favourite=True, manual=source == "practice", not_understood=True,
                cause="calculation", created_at=NOW, updated_at=NOW + timedelta(minutes=1),
            ))
        # Exercise additive fields without changing any column that existed in 0001.
        db.get(LearningSessionRecord, ids["active"]).options_snapshot = {
            "difficulty": [1, 2], "family_ids": ["historic-family"], "source": "frozen-options",
        }
        db.get(SeenTask, ids["seen"][5]).instance_key = _digest("synthetic-condition-identity")


@pytest.fixture(params=("sqlite", "postgresql"))
def recovery_database(request, tmp_path, monkeypatch, gate):
    tools = source = target = None
    if request.param == "sqlite":
        path = tmp_path / ("verify_recovery_" + uuid4().hex + ".sqlite3")
        gate.require_absent_path(path)
        database = Database(Settings(database_url=f"sqlite:///{path.as_posix()}"))
    else:
        if os.environ.get("OPS_RUN_POSTGRES_VERIFY") != "1":
            pytest.skip("Real PostgreSQL recovery requires OPS_RUN_POSTGRES_VERIFY=1 and clients")
        environment = gate.direct_environment(os.environ)
        for name in list(os.environ):
            if name.startswith("PG") and name not in environment:
                monkeypatch.delenv(name)
        for name, value in environment.items():
            if name.startswith("PG"):
                monkeypatch.setenv(name, value)
        tools = PostgresTools(environment=environment, timeout_seconds=120)
        source, target = "verify_recovery_source_" + uuid4().hex, "verify_restore_" + uuid4().hex
        write_new_json(tmp_path / "preserved-postgres-targets.json", {
            "source_database": source, "target_database": target, "automatic_cleanup": False,
        })
        gate.create_fresh_database(tools, source, purpose="recovery")
        database = Database(Settings(
            database_url=f"postgresql+psycopg:///{source}?connect_timeout=10",
        ))
    try:
        yield database, tools, source, target
    finally:
        database.dispose()


def test_full_populated_migration_and_backup_restore(recovery_database, tmp_path, gate):
    database, tools, source, target = recovery_database
    config, head = gate.migration_config(), gate.migration_head()
    with database.engine.begin() as connection:
        if source is not None:
            assert connection.scalar(text("SELECT current_database()")) == source
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_learning_core")
    original_tables = _tables(database, LEGACY_TABLES)
    assert all(not rows for rows in _snapshot(database, original_tables).values())
    ids, tasks = _seed_initial_orm(database, original_tables)
    before = _snapshot(database, original_tables)
    assert all(before.values())
    assert {row["id"] for row in before["guests"]} == {ids["owner"], ids["reviewer"]}
    assert {row["id"] for row in before["attempts"]} == set(ids["attempts"])
    assert {row["id"] for row in before["seen_tasks"]} == set(ids["seen"])
    assert {row["id"] for row in before["idempotency_records"]} == set(ids["idempotency"])
    assert {row["id"] for row in before["learning_sessions"]} == {ids["completed"], ids["active"]}
    assert all(row["tasks_snapshot"] == tasks for row in before["learning_sessions"])
    legacy_hashes = _fingerprints(before, original_tables)
    write_new_json(tmp_path / "populated-migration-before.json", {
        "revision": "0001_learning_core", "orm_seeded": True, "tables": legacy_hashes,
    })
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, head)
        assert list(connection.scalars(text("SELECT version_num FROM alembic_version"))) == [head]
    assert head != "0001_learning_core"
    assert _snapshot(database, original_tables) == before
    with database.transaction() as db:
        assert db.get(LearningSessionRecord, ids["active"]).options_snapshot is None
        assert db.get(SeenTask, ids["seen"][5]).instance_key is None
    write_new_json(tmp_path / "populated-migration-after.json", {
        "revision": head, "original_ids_and_snapshots_preserved": True,
        "tables": _fingerprints(_snapshot(database, original_tables), original_tables),
    })
    _seed_modern_orm(database, ids, tasks)
    assert _snapshot(database, original_tables) == before
    all_tables = _tables(database, inspect(database.engine).get_table_names())
    full_before = _snapshot(database, all_tables)
    assert set(all_tables) >= MODERN_TABLES | set(LEGACY_TABLES) | {"alembic_version"}
    assert all(full_before[name] for name in MODERN_TABLES)
    write_new_json(tmp_path / "populated-head-storage.json", {
        "migration_head": head, "tables": _fingerprints(full_before, all_tables),
        "dialect": database.engine.dialect.name, "live_postgres_fixture": tools is not None,
    })
    if tools is None:
        return
    backup = create_backup(
        tools, source=source, directory=tmp_path / "backups", expected_head=head,
    )
    bundle = tmp_path / "backups" / backup["backup_id"]
    manifest = read_bundle(bundle)
    write_new_json(tmp_path / "full-row-inventory-before.json", manifest["inventory"])
    result = restore_backup(tools, bundle=bundle, target=target, expected_head=head, source=source)
    with tools.session(target) as session:
        session.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        restored_inventory = export_inventory(session, head)
        session.query("COMMIT;")
    write_new_json(tmp_path / "full-row-inventory-after.json", restored_inventory)
    assert restored_inventory == manifest["inventory"]
    assert set(restored_inventory["tables"]) == set(full_before)
    assert all(result["table_counts"][name] > 0 for name in MODERN_TABLES | set(LEGACY_TABLES))
    restored = Database(Settings(database_url=f"postgresql+psycopg:///{target}?connect_timeout=10"))
    try:
        with restored.engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == target
        assert _snapshot(restored, original_tables) == before
        assert _snapshot(restored, all_tables) == full_before
    finally:
        restored.dispose()
    write_new_json(tmp_path / "full-postgres-restore-evidence.json", {
        "migration_head": head, "orm_seeded_initial_tables": list(LEGACY_TABLES),
        "populated_subsystem_tables": sorted(MODERN_TABLES),
        "original_ids_and_snapshots_preserved": True, "all_public_rows_preserved": True,
        "backup": backup, "restore": result,
    })


class _RecordingTools:
    def __init__(self, *, exists=False, populated=False):
        self.calls, self.exists, self.populated = [], exists, populated

    @contextmanager
    def session(self, database):
        self.calls.append(("connect", database))
        yield self

    def query(self, sql):
        self.calls.append(("query", sql))
        if "FROM pg_database" in sql:
            return ["1"] if self.exists else []
        if "FROM pg_catalog.pg_class" in sql:
            return ["1"] if self.populated else ["0"]
        return []


@pytest.mark.parametrize("name,purpose", [
    ("math_ege", "recovery"), ("postgres", "load"), ("verify_load_old", "load"),
    ("verify_restore_" + "a" * 32, "recovery"),
    ("verify_load_" + "a" * 32 + "'; SELECT 1; --", "load"),
    ("verify_load_" + "a" * 32, "unknown"),
])
def test_database_scope_rejected_before_any_connection(gate, name, purpose):
    tools = _RecordingTools()
    with pytest.raises(OperationError, match="new_namespaced_verification_database_required"):
        gate.create_fresh_database(tools, name, purpose=purpose)
    assert tools.calls == []


def test_database_absence_and_empty_guards_never_reuse_a_target(gate):
    name = "verify_recovery_source_" + uuid4().hex
    existing = _RecordingTools(exists=True)
    with pytest.raises(OperationError, match="verification_database_already_exists"):
        gate.create_fresh_database(existing, name, purpose="recovery")
    assert not any("CREATE DATABASE" in value for _, value in existing.calls)
    fresh = _RecordingTools()
    gate.create_fresh_database(fresh, name, purpose="recovery")
    assert fresh.calls[1][1].startswith("SELECT 1 FROM pg_database")
    assert fresh.calls[2] == ("query", f'CREATE DATABASE "{name}" WITH TEMPLATE template0;')
    assert fresh.calls[3] == ("connect", name)
    with pytest.raises(OperationError, match="new_verification_database_not_empty"):
        gate.create_fresh_database(_RecordingTools(populated=True), name, purpose="recovery")


def test_existing_artifacts_and_pytest_basetemp_are_never_cleared(gate, tmp_path):
    directory = tmp_path / "preserved"
    directory.mkdir()
    marker = directory / "existing-backup.dump"
    marker.write_bytes(b"preserve-these-bytes")
    with pytest.raises(OperationError, match="verification_artifacts_already_exist"):
        gate.reserve_directory(directory)
    with pytest.raises(OperationError, match="verification_artifact_already_exists"):
        gate.require_absent_path(directory)
    assert marker.read_bytes() == b"preserve-these-bytes"


def test_connection_environment_uses_explicit_pgpass_and_clears_ambient_overrides(gate, tmp_path):
    password_file = tmp_path / "pgpass"
    password_file.write_text("127.0.0.1:55432:*:verify_admin:synthetic\n", encoding="ascii")
    password_file.chmod(0o600)
    supplied = {
        "PGHOST": "127.0.0.1", "PGPORT": "55432", "PGUSER": "verify_admin",
        "PGPASSFILE": str(password_file), "PGPASSWORD": "ambient-password",
        "PGSERVICE": "production", "PGSERVICEFILE": "ambient-service", "PGHOSTADDR": "192.0.2.1",
        "PGOPTIONS": "unsafe-override", "PGDATABASE": "math_ege", "OPS_SOURCE_DATABASE": "math_ege",
        "DATABASE_URL": "postgresql+psycopg:///math_ege", "UVICORN_WORKERS": "8",
        "PYTEST_ADDOPTS": "--force-short-run", "ACCOUNTS_ENABLED": "true",
    }
    clean = gate.direct_environment(supplied)
    assert clean["PGPASSFILE"] == str(password_file)
    assert clean["PGDATABASE"] == "postgres"
    assert all(clean[name] == "" for name in (
        "PGPASSWORD", "PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGOPTIONS",
    ))
    child = gate.child_environment(clean)
    assert child["DATABASE_URL"] == "sqlite:///:memory:"
    assert child["ACCOUNTS_ENABLED"] == "false"
    assert not {"UVICORN_WORKERS", "PYTEST_ADDOPTS", "OPS_SOURCE_DATABASE"} & child.keys()
    for override in ({"OPS_PG_CONTAINER": "db"}, {"PGHOST": "db.example.invalid"}, {"PGPORT": ""}):
        with pytest.raises(OperationError):
            gate.direct_environment({**supplied, **override})


def test_original_and_missing_content_cannot_be_used_for_full_load(gate, tmp_path):
    with pytest.raises(OperationError, match="expanded_course_package_missing"):
        gate.content_inventory(tmp_path / "missing-course")
    with pytest.raises(OperationError, match="expanded_course_coverage_required"):
        gate.content_inventory(BACKEND / "content")


def test_postgres_readiness_has_a_deadline_and_requires_major_18(gate, monkeypatch):
    clock = [0.0]
    calls = []

    class Unready:
        def __init__(self, **kwargs):
            assert kwargs["timeout_seconds"] == 3

        def session(self, database):
            calls.append(database)
            raise OperationError("postgres_client_failed")

    monkeypatch.setattr(gate, "PostgresTools", Unready)
    monkeypatch.setattr(gate.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        gate.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    with pytest.raises(OperationError, match="postgres_readiness_deadline_exceeded"):
        gate.wait_for_postgres({}, seconds=2)
    assert clock == [2.0] and 1 <= len(calls) <= 4
    tools = _RecordingTools()
    tools.query = lambda sql: ["170007"]
    monkeypatch.setattr(gate, "PostgresTools", lambda **kwargs: tools)
    with pytest.raises(OperationError, match="verification_requires_postgres_18"):
        gate.wait_for_postgres({})


def test_postgres_client_major_must_match_the_pinned_server(gate, monkeypatch):
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(
        args[0], 0, stdout=b"psql (PostgreSQL) 17.7\n",
    ))
    with pytest.raises(OperationError, match="verification_requires_postgres_18_clients"):
        gate.client_versions({})


def _complete_report(config):
    return {
        "conditions": config.description(), "dry_run": False, "isolation_preflight_verified": True,
        "execution_complete": True, "workload_complete": True,
        "all_users_active_every_minute": True,
        "observed_client_thresholds_met": True, "full_control_scenario_completed": True,
        "requests_dispatched": 18000, "requests_finished": 18000, "http_statuses_received": 18000,
        "http_responses_completed": 18000, "guest_users_created": 500,
        "users_with_completed_session": 500, "logical_users_touched": 500,
        "missed_schedule_slots": 0, "disabled_users": 0, "bank_exhaustion_responses": 0,
        "bank_exhausted_users": 0, "server_errors": 0, "elapsed_seconds_including_drain": 600.1,
        "active_logical_users_per_minute": dict.fromkeys(map(str, range(10)), 500),
    }


@pytest.mark.parametrize("change,actual_seconds", [
    ({"dry_run": True}, 600.2), ({"full_control_scenario_completed": False}, 600.2),
    ({"observed_client_thresholds_met": False}, 600.2), ({"requests_finished": 17999}, 600.2),
    ({"bank_exhausted_users": 1}, 600.2), ({"missed_schedule_slots": 1}, 600.2),
    ({"elapsed_seconds_including_drain": 60}, 600.2), ({}, 60),
    ({"active_logical_users_per_minute": {"0": 500}}, 600.2),
    ({"conditions": {"logical_users": 500, "target_rps": 30, "duration_seconds": 60}}, 600.2),
])
def test_gate_rejects_partial_simulated_or_nonuseful_workloads(gate, change, actual_seconds):
    config = LoadConfig(
        target=gate.LOAD_TARGET, route="/api/v1", namespace="verify_load_" + uuid4().hex,
    )
    report = _complete_report(config)
    gate.require_full_workload(report, config, 600.2)
    with pytest.raises(OperationError):
        gate.require_full_workload({**report, **change}, config, actual_seconds)


def test_a_dead_api_never_reaches_the_load_transport(gate, monkeypatch):
    process = SimpleNamespace(poll=lambda: 1)
    calls = []
    monkeypatch.setattr(gate, "HttpTransport", lambda *args, **kwargs: calls.append("constructed"))
    config = LoadConfig(
        target=gate.LOAD_TARGET, route="/api/v1", namespace="verify_load_" + uuid4().hex,
    )
    with pytest.raises(OperationError, match="verification_api_exited_before_readiness"):
        gate.wait_for_api(process, config)
    assert calls == ["constructed"]


def test_recovery_junit_requires_both_real_tests_without_skips(gate, tmp_path):
    suite = ElementTree.Element("testsuite")
    cases = [ElementTree.SubElement(suite, "testcase", name=node.split("::")[1])
             for node in gate.RECOVERY_TESTS]
    good = tmp_path / "good.xml"
    ElementTree.ElementTree(suite).write(good)
    gate.require_recovery_junit(good)
    ElementTree.SubElement(cases[1], "skipped")
    skipped = tmp_path / "skipped.xml"
    ElementTree.ElementTree(suite).write(skipped)
    with pytest.raises(OperationError, match="both_live_recovery_tests_must_pass_without_skips"):
        gate.require_recovery_junit(skipped)


@pytest.mark.parametrize("phase", ("call", "collection", "internal"))
def test_recovery_plugin_removes_sensitive_exception_and_capture_before_junit(
    gate, tmp_path, phase,
):
    sentinel = "SYNTHETIC_PRIVATE_VALUE_MUST_NOT_REACH_REPORT"
    sample = tmp_path / "test_sanitized_sample.py"
    source = f"print({sentinel!r})\nraise ValueError({sentinel!r})\n"
    if phase == "call":
        source = "def test_failure():\n" + "".join(
            "    " + line for line in source.splitlines(True)
        )
    if phase == "internal":
        source = "def test_sample():\n    pass\n"
    sample.write_text(source, encoding="utf-8")
    junit = tmp_path / "sanitized.junit.xml"
    environment = gate.child_environment(os.environ)
    extra = []
    if phase == "internal":
        plugin = tmp_path / "synthetic_internal_failure.py"
        plugin.write_text(
            f"def pytest_collection_modifyitems():\n    raise ValueError({sentinel!r})\n",
            encoding="utf-8",
        )
        environment["PYTHONPATH"] = str(tmp_path) + os.pathsep + environment["PYTHONPATH"]
        extra = ["-p", "synthetic_internal_failure"]
    result = gate.run_child(
        [sys.executable, "-m", "pytest", str(sample), "--noconftest", "-q", "--tb=no",
         "--show-capture=no", "-p", "no:cacheprovider", "-p", "verify_postgres",
         "-o", "junit_logging=no", "--basetemp", str(tmp_path / "child-basetemp"),
         "--junitxml", str(junit), *extra],
        environment, seconds=30, evidence=tmp_path / "process.json",
    )
    assert result["exit_code"] != 0 and not result["timed_out"]
    content = junit.read_text(encoding="utf-8")
    assert sentinel not in content and "ValueError" not in content
    assert "postgres_verification_" in content
    tag = "failure" if phase == "call" else "error"
    assert ElementTree.fromstring(content).findall(".//" + tag)


def test_child_timeout_stops_process_and_preserves_evidence(gate, tmp_path):
    evidence = tmp_path / "timeout.json"
    result = gate.run_child(
        [sys.executable, "-c", "import time; time.sleep(60)"], gate.child_environment(os.environ),
        seconds=1, evidence=evidence,
    )
    assert result["timed_out"] and result["exit_code"] is not None
    assert json.loads(evidence.read_bytes()) == result
    with pytest.raises(OperationError, match="verification_artifact_already_exists"):
        gate.run_child(
            [sys.executable, "-c", "raise SystemExit(99)"], {}, seconds=1, evidence=evidence,
        )
    assert json.loads(evidence.read_bytes()) == result
