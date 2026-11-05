"""Operational boundaries use new temporary artifacts; no retention deletion is run."""

import hashlib
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import MetaData, Table, func, select, text
from sqlalchemy.engine import make_url
from starlette.routing import NoMatchFound

from app.accounts.models import (
    AccessSession,
    Account,
    AccountConsent,
    AccountDeletionRequest,
    GuestClaim,
    MagicLink,
    TotpCredential,
)
from app.accounts.tokens import token_digest
from app.assessments.models import AssessmentRecord
from app.config import Settings
from app.database import Database
from app.editor.models import EditorRevision
from app.learning.models import TaskAnnotation
from app.models import AttemptRecord, Guest, LearningSessionRecord
from app.operations.api import router as operations_router
from app.operations.backup import CORE_TABLES, create_backup, read_bundle, restore_backup
from app.operations.backup_cli import main as backup_main
from app.operations.common import (
    OperationError,
    json_bytes,
    publish_new_file,
    restore_target,
    write_new_json,
)
from app.operations.health import OperationHealth
from app.operations.load import (
    LoadConfig,
    LoadStatistics,
    Observation,
    VirtualUser,
    run_load,
    verify_empty_target,
)
from app.operations.load_cli import main as load_main
from app.operations.load_http import HttpTransport
from app.operations.postgres import PostgresTools
from app.operations.retention import apply_retention, retention_plan
from app.operations.rights import deletion_plan, deletion_status
from app.operations.rights_cli import main as rights_main
from app.operations.rights_cli import read_only_database

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
HEAD = "0005_editor"
NAMESPACE = "verify_load_" + uuid4().hex


class _FakePostgres:
    """A recording process boundary, never evidence of a live PostgreSQL restore."""

    def __init__(self):
        self.databases = {"math_ege"}
        self.transfers = []
        self.queries = []
        self.fail_dump = False
        self.wrong_inventory = False

    @contextmanager
    def session(self, database):
        yield _FakeSession(self, database)

    def transfer(self, program, database, arguments, *, source=None, destination=None):
        self.transfers.append((program, database, arguments))
        if program == "pg_dump":
            destination.write(b"PGDMP\x01\x02isolated-fake-archive")
            if self.fail_dump:
                raise OperationError("postgres_client_failed")
        else:
            assert source.read().startswith(b"PGDMP")


class _FakeSession:
    def __init__(self, tools, database):
        self.tools, self.database = tools, database

    def query(self, sql):
        self.tools.queries.append((self.database, sql))
        if sql.startswith("SHOW server_version_num"):
            return ["180006"]
        if "pg_export_snapshot()" in sql:
            return ["00000001-00000002-1"]
        if "FROM pg_catalog.pg_tables" in sql:
            return sorted(CORE_TABLES | {"accounts", "assessments", "editor_revisions"})
        if "FROM public.alembic_version" in sql:
            return [HEAD]
        if "FROM pg_database" in sql:
            return ["1"] if sql.split("'")[1] in self.tools.databases else []
        if sql.startswith("CREATE DATABASE"):
            target = sql.split('"')[1]
            if target in self.tools.databases:
                raise OperationError("postgres_query_failed")
            self.tools.databases.add(target)
        if "count(*) FROM pg_catalog.pg_class" in sql:
            return ["0"]
        return []

    def lines(self, sql):
        self.tools.queries.append((self.database, sql))
        table = sql.split('public."')[1].split('"')[0]
        count = 2 if table in {"learning_sessions", "attempts", "assessments"} else 1
        if self.tools.wrong_inventory and self.database.startswith("verify_restore_"):
            count += 1
        for index in range(count):
            yield hashlib.sha256(f"{table}:{index}".encode()).hexdigest()


@pytest.fixture
def backup_bundle(tmp_path):
    tools = _FakePostgres()
    root = tmp_path / "owned-backups"
    result = create_backup(tools, source="math_ege", directory=root, expected_head=HEAD, now=NOW)
    return tools, root, root / result["backup_id"]


def test_health_starts_unknown_keeps_last_success_and_bounds_backoff():
    tick = [50.0]
    health = OperationHealth(now=NOW, monotonic=lambda: tick[0])
    assert health.snapshot()["jobs"]["deadline_reconcile"]["status"] == "not_run"
    health.record_job("deadline_reconcile", True, NOW)
    for index in range(12):
        health.record_job("deadline_reconcile", False, NOW + timedelta(seconds=index + 1))
    job = health.snapshot()["jobs"]["deadline_reconcile"]
    assert job["last_success_at"] == NOW.isoformat()
    assert job["failures"] == 12 and job["backoff_seconds"] == 300
    assert health.retry_delay("deadline_reconcile", NOW + timedelta(seconds=20)) == 292
    health.record_job("deadline_reconcile", True, NOW + timedelta(seconds=21))
    tick[0] += 42
    snapshot = health.snapshot()
    assert snapshot["uptime_seconds"] == 42
    assert snapshot["jobs"]["deadline_reconcile"]["backoff_seconds"] == 0
    assert snapshot["jobs"]["deadline_reconcile"]["last_failure_at"] is not None
    snapshot["jobs"]["deadline_reconcile"]["successes"] = 999
    assert health.snapshot()["jobs"]["deadline_reconcile"]["successes"] == 2
    assert health.public_snapshot(database_ok=True) == {"status": "ok"}


def test_health_concurrency_and_fixed_labels_never_record_payloads():
    health = OperationHealth(now=NOW)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: health.record_event("attempt_save", False), range(400)))
    assert health.snapshot()["events"]["attempt_save"] == {"successes": 0, "failures": 400}
    private = "person@example.invalid?token=private-value"
    with pytest.raises(OperationError) as error:
        health.record_job(private, False, NOW)
    assert private not in str(error.value)
    assert private not in json.dumps(health.snapshot())
    with pytest.raises(OperationError):
        health.record_job("deadline_reconcile", "successful", NOW)
    with pytest.raises(OperationError):
        health.record_job("deadline_reconcile", True, NOW.replace(tzinfo=None))
    with pytest.raises(OperationError):
        health.record_job("deadline_reconcile", True, NOW - timedelta(seconds=1))


@pytest.mark.parametrize("target", [
    "math_ege", "postgres", "template0", "template1", "", "verify_restore_",
    "verify_restore_prod;DROP DATABASE math_ege", "verify_restore_x'", "-dmath_ege",
    "postgresql://user:private@localhost/math_ege", "verify_restore_" + "x" * 60,
    "verify_restore_x\n", "VERIFY_RESTORE_x", "verify_restore_тест", "verify_restore_x/y",
])
def test_restore_target_rejects_unsafe_or_unscoped_names(target):
    with pytest.raises(OperationError):
        restore_target(target, "math_ege")


def test_restore_target_also_checks_manifest_source_and_configured_production():
    name = "verify_restore_" + uuid4().hex
    assert restore_target(name, "math_ege") == name
    with pytest.raises(OperationError):
        restore_target(name, name)
    with pytest.raises(OperationError):
        restore_target(name, "math_ege", (name,))


def test_postgres_credentials_never_become_argv_or_repr():
    private = "not-a-real-password"
    tools = PostgresTools(container="math-ege-db-1", environment={
        "PATH": "path", "PGUSER": "math_ege", "PGPASSWORD": private,
        "PGPASSFILE": "/run/secrets/private-pgpass", "PGSERVICE": "unintended-target",
        "PGSERVICEFILE": "/run/secrets/private-service", "PGHOSTADDR": "192.0.2.1",
        "PGOPTIONS": "unintended-settings",
    })
    argv, env = tools.command("pg_dump", "math_ege", ("--format=custom", "--no-password"))
    assert argv[:3] == ["docker", "exec", "--interactive"]
    assert "PGPASSFILE" in argv and "/run/secrets/private-pgpass" not in argv
    assert private not in str(argv) and private not in repr(tools)
    assert not {"PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGOPTIONS", "PGPASSWORD"} & env.keys()
    assert env["PGDATABASE"] == "math_ege"


def test_postgres_environment_never_sets_empty_libpq_service_variables():
    # libpq reads an empty PGSERVICE/PGSERVICEFILE as present, then fails opening the
    # empty service file before any TCP connection. Neutralised overrides must be absent.
    tools = PostgresTools(environment={
        "PGUSER": "math_ege", "PGSERVICE": "production",
        "PGSERVICEFILE": "/run/secrets/private-service", "PGHOSTADDR": "192.0.2.1",
        "PGOPTIONS": "-c statement_timeout=0", "PGSYSCONFDIR": "/tmp",
    })
    argv, env = tools.command("psql", "postgres")
    assert argv == ["psql"]
    assert not {
        "PGSERVICE", "PGSERVICEFILE", "PGSYSCONFDIR", "PGHOSTADDR", "PGOPTIONS",
    } & env.keys()
    assert env["PGAPPNAME"] == "math_ege_operations"
    assert env["PGCLIENTENCODING"] == "UTF8"
    assert env["PGDATABASE"] == "postgres"


@pytest.mark.parametrize(("script", "expected_error"), [
    ("import sys; sys.stdout.buffer.write(b'PGDMP\\x00\\xff')", None),
    ("import sys; sys.stderr.write('private-diagnostic' * 65536)",
     "postgres_client_reported_diagnostics"),
    ("import sys; sys.stderr.write('private-diagnostic'); sys.exit(2)", "postgres_client_failed"),
    ("import time; time.sleep(30)", "postgres_client_failed_or_timed_out"),
])
def test_postgres_process_boundary_preserves_binary_and_redacts_errors(
    script, expected_error, tmp_path, monkeypatch, capsys,
):
    tools = PostgresTools(timeout_seconds=1, environment={"PGUSER": "math_ege"})
    command = PostgresTools.command

    def python_client(self, program, database, arguments):
        _, environment = command(self, program, database, arguments)
        return [sys.executable, "-c", script], environment

    monkeypatch.setattr(PostgresTools, "command", python_client)
    output = tmp_path / "subprocess-output.dump"
    with output.open("xb") as destination:
        if expected_error is None:
            tools.transfer("pg_dump", "math_ege", (), destination=destination)
        else:
            with pytest.raises(OperationError, match=expected_error) as error:
                tools.transfer("pg_dump", "math_ege", (), destination=destination)
            assert "private-diagnostic" not in str(error.value)
    if expected_error is None:
        assert output.read_bytes() == b"PGDMP\x00\xff"
    captured = capsys.readouterr()
    assert "private-diagnostic" not in captured.out + captured.err


def test_backup_is_unique_snapshot_bound_and_has_atomic_manifest(backup_bundle):
    tools, root, bundle = backup_bundle
    manifest = read_bundle(bundle)
    assert {path.name for path in bundle.iterdir()} == {"manifest.json", bundle.name + ".dump"}
    assert manifest["inventory"]["tables"]["attempts"]["rows"] == 2
    assert manifest["inventory"]["tables"]["assessments"]["rows"] == 2
    arguments = tools.transfers[0][2]
    assert "--snapshot=00000001-00000002-1" in arguments
    assert "--format=custom" in arguments
    assert any("REPEATABLE READ READ ONLY" in sql for _, sql in tools.queries)
    assert all("row_to_json" not in sql or "sha256" in sql for _, sql in tools.queries)
    original = (bundle / "manifest.json").read_bytes()
    second = create_backup(tools, source="math_ege", directory=root, expected_head=HEAD, now=NOW)
    assert second["backup_id"] != bundle.name
    assert (bundle / "manifest.json").read_bytes() == original


def test_failed_dump_preserves_partial_without_publishing_success(tmp_path):
    tools = _FakePostgres()
    tools.fail_dump = True
    with pytest.raises(OperationError):
        create_backup(tools, source="math_ege", directory=tmp_path, expected_head=HEAD, now=NOW)
    assert not list(tmp_path.glob("*/manifest.json"))
    assert len(list(tmp_path.glob("*/*.dump.partial"))) == 1


def test_atomic_publish_refuses_an_existing_file(tmp_path):
    temporary, existing = tmp_path / "new.partial", tmp_path / "existing.dump"
    temporary.write_bytes(b"new")
    existing.write_bytes(b"preserve")
    with pytest.raises(OperationError, match="refusing_to_replace_file"):
        publish_new_file(temporary, existing)
    assert existing.read_bytes() == b"preserve"
    assert temporary.read_bytes() == b"new"


def test_atomic_publish_refuses_a_racing_destination(tmp_path, monkeypatch):
    from app.operations import common

    temporary, destination = tmp_path / "new.partial", tmp_path / "claimed.dump"
    temporary.write_bytes(b"new")
    inspect_file = common.regular_file

    def racing_creator(path):
        inspect_file(path)
        destination.write_bytes(b"preserve-racing-file")

    monkeypatch.setattr(common, "regular_file", racing_creator)
    with pytest.raises(OperationError, match="refusing_to_replace_file"):
        publish_new_file(temporary, destination)
    assert destination.read_bytes() == b"preserve-racing-file"
    assert temporary.read_bytes() == b"new"


def test_restore_checks_new_target_then_compares_every_table(backup_bundle):
    tools, _, bundle = backup_bundle
    target = "verify_restore_" + uuid4().hex
    result = restore_backup(
        tools, bundle=bundle, target=target, source="math_ege", expected_head=HEAD,
    )
    assert result["all_row_and_snapshot_checksums_match"] is True
    assert result["table_counts"]["attempts"] == 2
    assert result["production_recovery_acceptance"] is False
    program, selected, arguments = tools.transfers[-1]
    assert program == "pg_restore" and selected == target
    assert "--exit-on-error" in arguments and "--single-transaction" in arguments
    assert "--clean" not in arguments and "--create" not in arguments
    count = len(tools.transfers)
    with pytest.raises(OperationError, match="restore_target_already_exists"):
        restore_backup(tools, bundle=bundle, target=target, source="math_ege", expected_head=HEAD)
    assert len(tools.transfers) == count


def test_restore_mismatch_is_failure_and_does_not_remove_new_database(backup_bundle):
    tools, _, bundle = backup_bundle
    tools.wrong_inventory = True
    target = "verify_restore_" + uuid4().hex
    with pytest.raises(OperationError, match="restored_history_or_snapshot_mismatch"):
        restore_backup(tools, bundle=bundle, target=target, source="math_ege", expected_head=HEAD)
    assert target in tools.databases
    assert (bundle / "manifest.json").exists()


def test_restore_corruption_and_wrong_head_fail_before_database_contact(backup_bundle):
    tools, _, bundle = backup_bundle
    before = len(tools.queries)
    with pytest.raises(OperationError, match="migration_head_mismatch"):
        restore_backup(tools, bundle=bundle, target="verify_restore_new", source="math_ege",
                       expected_head="unrelated_revision")
    assert len(tools.queries) == before
    archive = bundle / (bundle.name + ".dump")
    archive.write_bytes(archive.read_bytes()[:-1] + b"X")
    with pytest.raises(OperationError, match="archive_checksum_mismatch"):
        restore_backup(tools, bundle=bundle, target="verify_restore_new", source="math_ege",
                       expected_head=HEAD)
    assert len(tools.queries) == before


def test_manifest_cannot_redirect_restore_to_an_arbitrary_file(backup_bundle):
    _, _, bundle = backup_bundle
    path = bundle / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["archive"]["filename"] = "../../user-backup.dump"
    path.write_bytes(json_bytes(manifest))
    with pytest.raises(OperationError, match="archive_path_not_owned"):
        read_bundle(bundle)


def test_retention_is_exactly_thirty_days_read_only_and_scope_bound(backup_bundle, tmp_path):
    _, root, bundle = backup_bundle
    original = {path.name: path.read_bytes() for path in bundle.iterdir()}
    before_expiry = NOW + timedelta(days=30, microseconds=-1)
    assert retention_plan(root, now=before_expiry)["candidate_count"] == 0
    plan = retention_plan(root, now=NOW + timedelta(days=30))
    assert plan["dry_run"] and plan["candidate_count"] == 1
    assert plan["candidates"][0]["backup_id"] == bundle.name
    assert {path.name: path.read_bytes() for path in bundle.iterdir()} == original
    elsewhere = tmp_path / "other-root"
    elsewhere.mkdir()
    assert retention_plan(elsewhere, now=NOW + timedelta(days=30))["deletion_scope_sha256"] != (
        plan["deletion_scope_sha256"]
    )
    with pytest.raises(OperationError, match="exact_deletion_scope_confirmation_required"):
        apply_retention(root, confirmed_scope="wrong-scope")
    assert {path.name: path.read_bytes() for path in bundle.iterdir()} == original


def test_retention_refuses_unknown_files_and_preserves_unmanaged_backups(backup_bundle):
    _, root, bundle = backup_bundle
    (bundle / "user-notes.txt").write_text("preserve", encoding="utf-8")
    (root / "original-user-backup.dump").write_bytes(b"preserve")
    plan = retention_plan(root, now=NOW + timedelta(days=60))
    assert plan["candidate_count"] == 0 and plan["blocked_bundle_count"] == 1
    assert plan["unmanaged_entries_preserved"] == 1
    assert (root / "original-user-backup.dump").read_bytes() == b"preserve"


def test_backup_cli_dry_run_never_contacts_postgres_or_creates_files(tmp_path, monkeypatch, capsys):
    root = tmp_path / "not-yet-created"
    monkeypatch.setenv("OPS_SOURCE_DATABASE", "math_ege")
    monkeypatch.setenv("OPS_BACKUP_DIR", str(root))
    monkeypatch.setenv("PGUSER", "math_ege")
    monkeypatch.setattr(PostgresTools, "session", lambda *_: pytest.fail("database contacted"))
    assert backup_main(["backup", "--expected-head", HEAD, "--dry-run"]) == 0
    assert not root.exists()
    assert json.loads(capsys.readouterr().out)["database_contacted"] is False


@pytest.mark.parametrize("target", [
    "", "http://127.0.0.1", "http://localhost:8080", "http://example.invalid:8080",
    "http://127.0.0.1:8080/api/v1", "http://user:private@127.0.0.1:8080",
    "http://127.0.0.1:8080?token=private", "http://127.0.0.1:8080/#fragment",
    "file:///private", "http://127.0.0.1:99999",
])
def test_load_target_fails_closed(target):
    with pytest.raises(OperationError):
        LoadConfig(target, "/api/v1", NAMESPACE)


def test_load_requires_namespace_and_bounded_actual_conditions():
    with pytest.raises(OperationError):
        LoadConfig("http://127.0.0.1:8080", "/api/v1", "production")
    with pytest.raises(OperationError):
        LoadConfig("http://127.0.0.1:8080", "/api/v1/../../admin", NAMESPACE)
    with pytest.raises(OperationError):
        LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, max_in_flight=500)
    with pytest.raises(OperationError):
        LoadConfig("http://example.invalid:8080", "/api/v1", NAMESPACE, allow_remote_target=True)


def test_load_dry_run_and_parse_errors_are_redacted(monkeypatch, capsys):
    monkeypatch.setenv("OPS_LOAD_TARGET", "http://127.0.0.1:8080")
    monkeypatch.setenv("OPS_VERIFICATION_NAMESPACE", NAMESPACE)
    monkeypatch.setattr("app.operations.load_cli.run_load", lambda *_: pytest.fail("load executed"))
    assert load_main(["--target-route", "/api/v1"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["http_requests_sent"] == 0
    assert result["conditions"]["planned_requests"] == 18000
    assert result["conditions"]["max_in_flight_http_requests"] == 30
    private = "http://user:do-not-print@example.invalid:443"
    assert load_main(["--target-route", "/api/v1", "--unexpected", private]) == 2
    assert "do-not-print" not in capsys.readouterr().out


def test_load_bank_exhaustion_is_reported_without_false_pass():
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, users=1,
                        duration_seconds=1, requests_per_second=3)
    stats = LoadStatistics()
    stats.dispatched = 3
    stats.observe(Observation(0, "guest", 200, 1, "success", True), 0)
    stats.observe(Observation(0, "attempt", 200, 2, "success", True), 0.3)
    stats.observe(Observation(0, "create_session", 409, 5, "bank_exhausted", True), 0.6)
    result = stats.report(config, 1)
    assert result["bank_exhaustion_responses"] == 1
    assert result["server_errors"] == 0
    assert result["observed_client_thresholds_met"] is False
    assert result["full_control_scenario_completed"] is False
    assert result["p50_ms"] == 2 and result["p95_ms"] == 5 and result["max_ms"] == 5


def test_load_errors_and_missed_schedule_are_not_hidden():
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, users=1,
                        duration_seconds=1, requests_per_second=3)
    stats = LoadStatistics()
    stats.dispatched, stats.missed_schedule_slots = 2, 1
    stats.observe(Observation(0, "attempt", 503, 10, "http_error", True), 0)
    stats.observe(Observation(0, "profile", 0, 5000, "transport_error", True), 0.3)
    result = stats.report(config, 5)
    assert result["http_responses_completed"] == 1
    assert result["requests_finished"] == 2
    assert result["server_error_rate"] == 1
    assert result["execution_complete"] is False
    assert result["observed_client_thresholds_met"] is False


def test_full_load_request_count_alone_does_not_prove_completed_workload():
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE)
    stats = LoadStatistics()
    stats.dispatched = config.planned_requests
    for index in range(config.planned_requests):
        stats.observe(
            Observation(index % config.users, "health", 200, 1, "success", True),
            index / config.requests_per_second,
        )
    result = stats.report(config, config.duration_seconds)
    assert result["execution_complete"] is True
    assert result["full_control_scenario_completed"] is False


@pytest.mark.parametrize("outcome", ["success", "bank_exhausted", "http_error"])
def test_full_load_report_requires_successful_user_workflows(outcome):
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE)
    stats = LoadStatistics()
    stats.dispatched = config.planned_requests
    workflow = (
        "guest", "profile", "create_session", "get_session", "draft", "attempt", "health", "finish",
    )
    for index in range(config.planned_requests):
        operation = workflow[(index // config.users) % len(workflow)]
        result = outcome if index == 2 * config.users else "success"
        status = {"success": 200, "bank_exhausted": 409, "http_error": 503}[result]
        stats.observe(
            Observation(index % config.users, operation, status, 1, result, True),
            index / config.requests_per_second,
        )
    report = stats.report(config, config.duration_seconds)
    assert report["execution_complete"] is True
    assert report["users_with_completed_session"] == 500
    assert report["full_control_scenario_completed"] is (outcome == "success")
    assert report["observed_client_thresholds_met"] is (outcome == "success")
    assert report["bank_exhaustion_responses"] == (outcome == "bank_exhausted")


def test_load_keeps_known_server_errors_when_response_body_is_incomplete():
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, users=1,
                        duration_seconds=1, requests_per_second=1)
    stats = LoadStatistics()
    stats.dispatched = 1
    stats.observe(Observation(0, "attempt", 503, 10, "transport_error", True), 0)
    result = stats.report(config, 1)
    assert result["http_responses_completed"] == 0
    assert result["server_errors"] == 1 and result["server_error_rate"] == 1
    assert result["execution_complete"] is False


@pytest.fixture
def operational_http_server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def handle_request(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            calls.append({
                "method": self.command, "path": self.path, "body": body,
                "cookie": self.headers.get("Cookie"), "origin": self.headers.get("Origin"),
                "requested_with": self.headers.get("X-Requested-With"),
                "idempotency_key": self.headers.get("Idempotency-Key"),
                "namespace": self.headers.get("X-Math-Ege-Verification"),
            })
            if self.path == "/truncated":
                self.send_response(503)
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                self.wfile.write(b"20\r\nprivate-response-fragment")
                self.close_connection = True
                return
            self.send_response(302 if self.path == "/redirect" else 200)
            if self.path == "/redirect":
                self.send_header("Location", "/redirect-must-not-be-followed")
            if self.path == "/api/v1/guest":
                self.send_header("Set-Cookie", "guest=fixture; HttpOnly; SameSite=Lax; Path=/")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "32" if self.path == "/short-length" else "2")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = do_POST = do_PUT = handle_request

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()


def test_http_transport_uses_real_isolated_cookies_csrf_and_idempotency(
    operational_http_server, monkeypatch,
):
    origin, calls = operational_http_server
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    first = HttpTransport(origin, namespace=NAMESPACE, timeout_seconds=2)
    second = HttpTransport(origin, namespace=NAMESPACE, timeout_seconds=2)
    first.request("POST", "/api/v1/guest", {})
    key = str(uuid4())
    first.request("POST", "/api/v1/sessions", {"length": 5}, key)
    second.request("GET", "/api/v1/health")
    assert first.has_cookie and not second.has_cookie
    assert calls[0]["cookie"] is None and calls[1]["cookie"] == "guest=fixture"
    assert calls[2]["cookie"] is None
    assert calls[1]["origin"] == origin and calls[1]["requested_with"] == "math-ege"
    assert calls[1]["idempotency_key"] == key
    assert calls[1]["namespace"] == NAMESPACE
    assert json.loads(calls[1]["body"]) == {"length": 5}


def test_http_transport_does_not_follow_redirects(operational_http_server):
    origin, calls = operational_http_server
    transport = HttpTransport(origin, namespace=NAMESPACE, timeout_seconds=2)
    assert transport.request("GET", "/redirect") == (302, {})
    assert [call["path"] for call in calls] == ["/redirect"]


def test_http_transport_redacts_incomplete_response_and_retains_status(operational_http_server):
    origin, _ = operational_http_server
    transport = HttpTransport(origin, namespace=NAMESPACE, timeout_seconds=2)
    with pytest.raises(OperationError) as error:
        transport.request("GET", "/truncated")
    assert "private-response-fragment" not in str(error.value)
    assert error.value.status_code == 503


def test_http_transport_requires_complete_declared_body(operational_http_server):
    origin, _ = operational_http_server
    transport = HttpTransport(origin, namespace=NAMESPACE, timeout_seconds=2)
    with pytest.raises(OperationError, match="load_response_incomplete") as error:
        transport.request("GET", "/short-length")
    assert error.value.status_code == 200


def test_http_transport_response_cap_is_enforced(operational_http_server, monkeypatch):
    origin, _ = operational_http_server
    monkeypatch.setattr("app.operations.load_http.MAX_RESPONSE_BYTES", 1)
    transport = HttpTransport(origin, namespace=NAMESPACE, timeout_seconds=2)
    with pytest.raises(OperationError, match="load_response_size_exceeded") as error:
        transport.request("GET", "/api/v1/health")
    assert error.value.status_code == 200


def test_scheduler_bounds_real_threads_and_serializes_each_user():
    guard = Lock()
    peak, active, overlaps = [0], [0], []

    class SlowTransport:
        has_cookie = True

        def __init__(self, *_, **__):
            self.busy = False
            self.guest = str(uuid4())

        def request(self, method, path, body=None, key=None):
            if path.endswith("/operations/load-target"):
                return 200, {
                    "version": "1", "namespace": NAMESPACE, "database_namespace": NAMESPACE,
                    "empty": True, "counts": {"guests": 0, "learning_sessions": 0, "attempts": 0},
                }
            with guard:
                overlaps.append(self.busy)
                self.busy = True
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.25)
            with guard:
                self.busy = False
                active[0] -= 1
            if path.endswith("/guest"):
                return 200, {"id": self.guest}
            if path.endswith("/profile"):
                return 200, {"slots": [{"number": 6}]}
            return 503, {"error": {"code": "test_delay"}}

    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, users=2,
                        duration_seconds=1, requests_per_second=30, max_in_flight=2)
    result = run_load(config, transport_factory=SlowTransport)
    assert 1 <= peak[0] <= 2 and not any(overlaps)
    assert result["max_observed_in_flight_http_requests"] <= 2
    assert result["missed_schedule_slots"] > 0
    assert result["requests_dispatched"] + result["missed_schedule_slots"] == 30
    assert result["requests_finished"] == result["requests_dispatched"]
    assert result["elapsed_seconds_including_drain"] >= 1
    assert result["full_control_scenario_completed"] is False


def _mount_operations(client):
    try:
        client.app.url_path_for("load_target")
    except NoMatchFound:
        client.app.include_router(operations_router)


class _ClientTransport:
    def __init__(self, client):
        self.client = client

    @property
    def has_cookie(self):
        return bool(self.client.cookies)

    def request(self, method, path, body=None, key=None):
        headers = {"Idempotency-Key": key} if key else {}
        response = self.client.request(method, path, json=body, headers=headers)
        return response.status_code, response.json()


def test_isolation_preflight_uses_actual_database_and_refuses_existing_history(
    client_factory, tmp_path, monkeypatch,
):
    namespace = "verify_load_" + uuid4().hex
    monkeypatch.setenv("OPS_VERIFICATION_NAMESPACE", namespace)
    client = client_factory(
        database_url=f"sqlite:///{(tmp_path / (namespace + '.sqlite3')).as_posix()}",
        environment="verification",
    )
    _mount_operations(client)
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", namespace)
    transport = _ClientTransport(client)
    verify_empty_target(transport, config)
    assert client.post("/api/v1/guest", json={}).status_code == 200
    with pytest.raises(OperationError, match="empty_database_not_verified"):
        verify_empty_target(transport, config)
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Guest)) == 1
    monkeypatch.setenv("OPS_VERIFICATION_NAMESPACE", "verify_load_" + uuid4().hex)
    assert client.get("/api/v1/operations/load-target").status_code == 404


def test_ordinary_environment_does_not_expose_load_target(client):
    _mount_operations(client)
    assert client.get("/api/v1/operations/load-target").status_code == 404


def test_preflight_checks_connected_database_instead_of_engine_url(
    client_factory, tmp_path, monkeypatch,
):
    namespace = "verify_load_" + uuid4().hex
    monkeypatch.setenv("OPS_VERIFICATION_NAMESPACE", namespace)
    client = client_factory(environment="verification")
    _mount_operations(client)
    declared_url = make_url(f"sqlite:///{(tmp_path / (namespace + '.sqlite3')).as_posix()}")
    monkeypatch.setattr(client.app.state.database.engine, "url", declared_url)
    response = client.get("/api/v1/operations/load-target")
    assert response.status_code == 404
    assert "database_namespace" not in response.text


def test_virtual_user_executes_real_guest_draft_attempt_finish_protocol(client):
    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, users=1)
    user = VirtualUser(0, config, _ClientTransport(client))
    seen = []
    while user.session_number < 1 and len(seen) < 50:
        result = user.step()
        seen.append(result.operation)
        assert result.outcome == "success"
        assert result.status_code == 200
        assert not user.failed
    assert user.session_number == 1 and seen.count("guest") == 1
    assert seen.count("draft") == seen.count("attempt") == 5
    with client.app.state.database.transaction() as db:
        assert db.scalar(select(func.count()).select_from(Guest)) == 1
        assert db.scalar(select(func.count()).select_from(AttemptRecord)) == 5
        assert db.scalar(select(LearningSessionRecord.status)) == "completed"


def test_virtual_user_retries_idempotent_body_and_never_retries_guest_creation():
    class FailingTransport:
        has_cookie = True

        def __init__(self):
            self.calls = []

        def request(self, *args):
            self.calls.append(args)
            raise OperationError("load_transport_failed")

    config = LoadConfig("http://127.0.0.1:8080", "/api/v1", NAMESPACE, users=1)
    transport = FailingTransport()
    user = VirtualUser(0, config, transport, phase="create_session", guest_created=True, slots=[6])
    user.step()
    user.step()
    assert transport.calls[0] == transport.calls[1]
    assert canonical_key(transport.calls[0][3])
    first = VirtualUser(1, config, FailingTransport())
    first.step()
    assert first.failed


def canonical_key(value):
    from uuid import UUID

    return str(UUID(value)) == value


@pytest.fixture
def rights_database(tmp_path):
    url = f"sqlite:///{(tmp_path / 'rights.sqlite3').as_posix()}"
    database = Database(Settings(database_url=url))
    database.create_schema_for_tests()
    accounts, requests = [str(uuid4()), str(uuid4())], [str(uuid4()), str(uuid4())]
    roots, linked = [str(uuid4()), str(uuid4())], str(uuid4())
    with database.transaction(write=True) as db:
        for index, guest_id in enumerate([*roots, linked]):
            db.add(Guest(id=guest_id, token_digest=str(index + 1) * 64, created_at=NOW,
                         expires_at=NOW + timedelta(days=180), last_seen_at=NOW))
        db.flush()
        for index, account_id in enumerate(accounts):
            db.add(Account(id=account_id, email=f"private-{index}@example.invalid",
                           root_guest_id=roots[index], role="student", created_at=NOW,
                           email_verified_at=NOW, policy_version="test-1", consented_at=NOW,
                           daily_minutes=20))
        db.flush()
        for index, account_id in enumerate(accounts):
            requested = NOW - timedelta(days=31) if index == 0 else NOW
            db.add(AccountDeletionRequest(
                id=requests[index], account_id=account_id, requested_at=requested,
                deadline_at=requested + timedelta(days=30), status="requested",
            ))
            db.add(AccountConsent(id=str(uuid4()), account_id=account_id, policy_version="test-1",
                                  accepted_at=NOW))
        db.add(GuestClaim(guest_id=linked, account_id=accounts[0], claimed_at=NOW))
        db.add(MagicLink(
            id=str(uuid4()), email="private-0@example.invalid", token_digest="9" * 64,
            browser_state_digest="8" * 64, browser_credential_digest=None, guest_id=linked,
            policy_version="test-1", created_at=NOW, expires_at=NOW + timedelta(minutes=15),
            consumed_at=None,
        ))
        for owner in [*roots, linked]:
            db.add(TaskAnnotation(
                id=str(uuid4()), owner_id=owner, session_id=str(uuid4()), task_id="fixture-task",
                source="practice", favourite=True, manual=False, not_understood=False,
                cause=None, created_at=NOW, updated_at=NOW,
            ))
    try:
        yield database, accounts, requests
    finally:
        database.dispose()


def test_data_rights_is_scoped_count_only_and_pending_is_not_fulfilled(rights_database):
    database, accounts, requests = rights_database
    with database.engine.connect() as connection:
        status = deletion_status(connection, NOW)
        plan = deletion_plan(connection, account_id=accounts[0], request_id=requests[0], now=NOW)
        assert status["requested_count"] == 2 and status["overdue_count"] == 1
        assert plan["counts"]["guests"] == 2
        assert plan["counts"]["learning_annotations"] == 2
        assert plan["counts"]["account_magic_links"] == 1
        assert plan["deadline_reached"] is True
        assert plan["fulfillment_available"] is True
        assert plan["guest_cleanup_enabled"] is False
        with pytest.raises(OperationError, match="scope_mismatch"):
            deletion_plan(connection, account_id=accounts[0], request_id=requests[1], now=NOW)
        serialized = json.dumps(plan) + json.dumps(status)
        assert "private-" not in serialized
        assert not any(value in serialized for value in [*accounts, *requests])
        assert "token_digest" not in serialized and "browser_state" not in serialized
        assert connection.scalar(select(func.count()).select_from(AccountDeletionRequest)) == 2


@pytest.mark.parametrize("scope", [
    "", "*", "1=1", "' OR true", "00000000-0000-0000-0000-000000000000",
])
def test_data_rights_pathological_scope_fails_before_query(scope, rights_database):
    database, _, requests = rights_database
    with database.engine.connect() as connection, pytest.raises(OperationError):
        deletion_plan(connection, account_id=scope, request_id=requests[0], now=NOW)


def test_read_only_rights_cli_preserves_database_bytes(rights_database, monkeypatch, capsys):
    database, _, _ = rights_database
    path = Path(database.engine.url.database)
    before = path.read_bytes()
    monkeypatch.setenv("OPS_DATABASE_URL", str(database.engine.url))
    assert rights_main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["fulfillment_available"] is True
    assert path.read_bytes() == before
    with read_only_database(str(database.engine.url)) as connection:
        # Confirm the read-only handle opened the same populated database.
        assert connection.scalar(select(func.count()).select_from(Account)) == 2
    assert path.read_bytes() == before


def test_read_only_rights_counts_use_one_snapshot_during_concurrent_updates(rights_database):
    database, _, requests = rights_database
    with closing(sqlite3.connect(database.engine.url.database)) as setup:
        setup.execute("PRAGMA journal_mode=WAL")
    with read_only_database(str(database.engine.url)) as connection:
        before = deletion_status(connection, NOW)
        with database.transaction(write=True) as db:
            pending = db.get(AccountDeletionRequest, requests[1])
            pending.requested_at = NOW - timedelta(days=31)
            pending.deadline_at = NOW - timedelta(days=1)
        assert deletion_status(connection, NOW) == before
    with read_only_database(str(database.engine.url)) as connection:
        assert deletion_status(connection, NOW)["overdue_count"] == 2


def test_read_only_rights_does_not_create_missing_sqlite(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(OSError), read_only_database(f"sqlite:///{path.as_posix()}"):
        pytest.fail("missing database opened")
    assert not path.exists()


def test_staff_diagnostics_require_role_and_recent_mfa(client):
    _mount_operations(client)
    app = client.app
    app.state.operation_health = OperationHealth(now=NOW)
    app.state.operation_health.record_job("deadline_reconcile", False, NOW)
    app.state.accounts = SimpleNamespace(
        available=True,
        config=SimpleNamespace(mfa_encryption_key="test-only-not-used-for-decryption"),
        database=app.state.database, clock=lambda: NOW,
    )
    assert client.get("/api/v1/operations/health").status_code == 401
    guest, account, access = str(uuid4()), str(uuid4()), str(uuid4())
    from app.accounts.tokens import new_token

    credential = new_token()
    with app.state.database.transaction(write=True) as db:
        db.add(Guest(id=guest, token_digest="a" * 64, created_at=NOW,
                     expires_at=NOW + timedelta(days=180), last_seen_at=NOW))
        db.flush()
        db.add(Account(id=account, email="staff-private@example.invalid", root_guest_id=guest,
                       role="methodist", created_at=NOW, email_verified_at=NOW,
                       policy_version="test-1", consented_at=NOW, daily_minutes=20))
        db.flush()
        db.add(AccessSession(id=access, account_id=account, token_digest=token_digest(credential),
                             created_at=NOW, expires_at=NOW + timedelta(days=1), last_seen_at=NOW,
                             revoked_at=None, mfa_verified_at=None))
    client.cookies.set(app.state.settings.cookie_name, credential)
    denied = client.get("/api/v1/operations/health")
    assert denied.status_code == 403 and "jobs" not in denied.text
    with app.state.database.transaction(write=True) as db:
        db.get(AccessSession, access).mfa_verified_at = NOW
        db.add(TotpCredential(account_id=account, secret_ciphertext="encrypted-fixture",
                              enrollment_session_id=access, enrollment_expires_at=NOW,
                              confirmed_at=NOW, last_timecode=-1, attempts=[]))
    accepted = client.get("/api/v1/operations/health")
    assert accepted.status_code == 200
    assert accepted.json()["jobs"]["deadline_reconcile"]["failures"] == 1
    assert credential not in accepted.text and "staff-private" not in accepted.text
    with app.state.database.transaction(write=True) as db:
        db.get(Account, account).role = "student"
    assert client.get("/api/v1/operations/health").status_code == 403


@pytest.fixture(params=["sqlite", "postgresql"])
def operational_migration_database(request, tmp_path, monkeypatch):
    if request.param == "sqlite":
        url = f"sqlite:///{(tmp_path / 'migration.sqlite3').as_posix()}"
        return Database(Settings(database_url=url)), None, None, None
    if os.environ.get("OPS_RUN_POSTGRES_VERIFY") != "1":
        pytest.skip("Live PostgreSQL recovery requires OPS_RUN_POSTGRES_VERIFY=1")
    if os.environ.get("OPS_PG_CONTAINER") or not all(
        os.environ.get(name) for name in ("PGHOST", "PGPORT", "PGUSER")
    ):
        raise OperationError("postgres_test_requires_explicit_direct_host_port_and_role")
    tools = PostgresTools(timeout_seconds=120)
    _, environment = tools.command("psql", "postgres")
    for name in list(os.environ):
        if name.startswith("PG") and name not in environment:
            monkeypatch.delenv(name)
    for name, value in environment.items():
        if name.startswith("PG"):
            monkeypatch.setenv(name, value)
    source, target = "verify_restore_source_" + uuid4().hex, "verify_restore_" + uuid4().hex
    write_new_json(tmp_path / "preserved-postgres-targets.json", {
        "source_database": source, "target_database": target, "automatic_cleanup": False,
    })
    with tools.session("postgres") as admin:
        admin.query(f'CREATE DATABASE "{source}" WITH TEMPLATE template0;')
    database = Database(Settings(
        database_url=f"postgresql+psycopg:///{source}?connect_timeout=10",
    ))
    return database, tools, source, target


def _populate_restore_history(database, guest):
    """Storage fixtures include distinct frozen results and content/profile revisions."""
    account = str(uuid4())
    with database.transaction(write=True) as db:
        db.add(Account(
            id=account, email="restore-fixture@example.invalid", root_guest_id=guest,
            role="student", created_at=NOW, email_verified_at=NOW, policy_version="test-1",
            consented_at=NOW, daily_minutes=20,
        ))
        db.add(AssessmentRecord(
            id=str(uuid4()), guest_id=guest, profile_id="historic-profile",
            profile_revision="historic-profile-1", profile_snapshot={"revision": "original"},
            tasks_snapshot=[{"id": "old-task", "answer": "2,5", "revision": "old-task-1"}],
            mode="exam", status="completed", created_at=NOW, started_at=NOW,
            deadline_at=NOW + timedelta(minutes=60), released_at=NOW + timedelta(minutes=60),
            duration_minutes=60, writer_device_id=str(uuid4()), writer_generation=1,
            draft_revision=1, current_index=0, drafts={}, first_drafts={}, answer_context={},
            server_result={"score": 1, "answer": "2,5"},
            local_result={"score": 0, "answer": "2,6"}, finish_hash="b" * 64,
        ))
        for kind in ("profile", "task"):
            payload = {"id": "historic-" + kind, "revision": "original", "value": "2,50"}
            db.add(EditorRevision(
                id=str(uuid4()), kind=kind, content_id="historic-" + kind, version=1, revision=1,
                status="draft", title="Restore storage fixture", payload=payload,
                payload_hash=hashlib.sha256(json_bytes(payload)).hexdigest(),
                author_id=account, change_note="Synthetic storage verification",
                created_at=NOW, updated_at=NOW,
            ))


def test_populated_initial_migration_preserves_ids_history_and_frozen_snapshots(
    tmp_path, operational_migration_database,
):
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    database, tools, source, target = operational_migration_database
    try:
        with database.engine.begin() as connection:
            if tools is not None:
                assert connection.scalar(text("SELECT current_database()")) == source
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "0001_learning_core")
        guest, session, attempt = str(uuid4()), str(uuid4()), str(uuid4())
        with database.engine.begin() as connection:
            connection.execute(Guest.__table__.insert(), {
                "id": guest, "token_digest": "a" * 64, "created_at": NOW,
                "expires_at": NOW + timedelta(days=180), "last_seen_at": NOW,
            })
            connection.execute(LearningSessionRecord.__table__.insert(), {
                "id": session, "guest_id": guest, "profile_id": "old-profile",
                "profile_revision": "old-profile-1",
                "profile_snapshot": {"revision": "old-profile-1"},
                "mode": "practice", "status": "completed", "created_at": NOW,
                "completed_at": NOW, "current_index": 0, "requested_length": 5, "notice": None,
                "draft_revision": 1, "tasks_snapshot": [{"id": "old-task", "answer": "2,5"}],
                "drafts": {"old-task": {"answer": "2.50", "active_seconds": 10}},
                "help_state": {}, "active_seconds": {"old-task": 10},
                "summary_snapshot": {"independent_total": 1, "independent_correct": 1},
            })
            connection.execute(AttemptRecord.__table__.insert(), {
                "id": attempt, "guest_id": guest, "session_id": session, "task_id": "old-task",
                "task_revision": "old-task-1", "sequence": 1, "raw_answer": "2.50",
                "normalized_answer": "2,5", "correct": True, "assisted": False,
                "first_attempt": True, "independent": True, "skipped": False, "active_seconds": 10,
                "created_at": NOW, "checker_revision": "checker-1", "expected_answer": "2,5",
                "solution": ["Original explanation"],
            })

        def snapshot():
            with database.engine.connect() as connection:
                return {
                    name: list(connection.execute(
                        select(table).order_by(*table.primary_key),
                    ).mappings()) for name, table in original_tables.items()
                }

        with database.engine.connect() as connection:
            # Freeze the original columns; additive columns may legitimately appear at head.
            original_tables = {
                name: Table(name, MetaData(), autoload_with=connection)
                for name in sorted(CORE_TABLES - {"alembic_version"})
            }
        before = snapshot()
        with database.engine.begin() as connection:
            cfg.attributes["connection"] = connection
            command.upgrade(cfg, "head")
        assert snapshot() == before
        with database.engine.connect() as connection:
            current = list(connection.scalars(text("SELECT version_num FROM alembic_version")))
        assert current == ScriptDirectory.from_config(cfg).get_heads()
        assert current != ["0001_learning_core"]
        assert before["attempts"][0]["id"] == attempt
        assert before["learning_sessions"][0]["tasks_snapshot"] == [
            {"id": "old-task", "answer": "2,5"},
        ]
        _populate_restore_history(database, guest)
        assert snapshot() == before
        if tools is not None:
            backup = create_backup(
                tools, source=source, directory=tmp_path / "backups", expected_head=current[0],
            )
            restored = restore_backup(
                tools, source=source, target=target,
                bundle=tmp_path / "backups" / backup["backup_id"], expected_head=current[0],
            )
            for name in ("accounts", "assessments", "guests", "attempts", "learning_sessions"):
                assert restored["table_counts"][name] == 1
            assert restored["table_counts"]["editor_revisions"] == 2
            write_new_json(tmp_path / "postgres-restore-evidence.json", {
                "populated_migration_preserved_original_rows": True,
                "backup": backup, "restore": restored,
            })
    finally:
        database.dispose()
