"""Linux CI recovery/load gate. Every database and evidence directory is new.

Run with the project's dev venv. This module is also a pytest plugin which removes
exception text and captured output BEFORE the recovery JUnit report is written.
"""

import json
import os
import platform
import re
import signal
import socket
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.content import load_content  # noqa: E402
from app.operations.backup import create_backup  # noqa: E402
from app.operations.common import (  # noqa: E402
    OperationError,
    SafeArgumentParser,
    file_sha256,
    identifier,
    no_links,
    print_json,
    private_directory,
    regular_file,
    revision,
    verification_namespace,
    write_new_json,
)
from app.operations.load import LoadConfig, verify_empty_target  # noqa: E402
from app.operations.load_http import HttpTransport  # noqa: E402
from app.operations.postgres import PostgresTools  # noqa: E402

RECOVERY_TESTS = (
    "tests/test_operations.py::"
    "test_populated_initial_migration_preserves_ids_history_and_frozen_snapshots[postgresql]",
    "tests/test_postgres_recovery.py::"
    "test_full_populated_migration_and_backup_restore[postgresql]",
)
LOAD_TARGET = "http://127.0.0.1:8001"


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport():
    report = yield
    report.sections = []
    report.user_properties = []
    if report.failed:
        report.longrepr = "postgres_verification_test_failed_" + report.when
    elif report.skipped:
        report.longrepr = ("postgres-verification", 0, "live_postgres_test_skipped")
    return report


@pytest.hookimpl(tryfirst=True)
def pytest_collectreport(report):
    report.sections = []
    if report.failed:
        report.longrepr = "postgres_verification_collection_failed"
    elif report.skipped:
        report.longrepr = "postgres_verification_collection_skipped"


@pytest.hookimpl(tryfirst=True)
def pytest_internalerror(excrepr):
    # JUnit handles framework errors through a separate hook, bypassing TestReport.
    # TerminalRepr.__str__ delegates to this renderer; sanitize before any consumer.
    def render(writer):
        writer.line("postgres_verification_internal_error")

    excrepr.toterminal = render


def reserve_directory(path: Path) -> Path:
    """In particular, never give pytest an existing --basetemp to clear."""
    directory = private_directory(path)
    try:
        directory.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        raise OperationError("verification_artifacts_already_exist") from None
    return directory


def require_absent_path(path: Path) -> None:
    no_links(path)
    if path.exists():
        raise OperationError("verification_artifact_already_exists")


def migration_config() -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    return config


def migration_head() -> str:
    heads = ScriptDirectory.from_config(migration_config()).get_heads()
    if len(heads) != 1:
        raise OperationError("verification_requires_one_migration_head")
    return revision(heads[0])


def direct_environment(environment: Mapping[str, str]) -> dict[str, str]:
    if environment.get("OPS_PG_CONTAINER") or environment.get("PGHOST") not in {
        "127.0.0.1", "::1",
    }:
        raise OperationError("verification_requires_direct_loopback_postgres")
    port = environment.get("PGPORT", "")
    if not re.fullmatch(r"[0-9]{1,5}", port) or not 1 <= int(port) <= 65535:
        raise OperationError("verification_requires_explicit_postgres_port")
    identifier(environment.get("PGUSER", ""))
    password_file = Path(environment.get("PGPASSFILE", ""))
    if not password_file.is_absolute():
        raise OperationError("verification_requires_external_pgpassfile")
    regular_file(password_file)
    if os.name == "posix" and password_file.stat().st_mode & 0o077:
        raise OperationError("verification_pgpassfile_must_be_private")
    tools = PostgresTools(environment=environment)
    _, clean = tools.command("psql", "postgres")
    return clean


def child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    clean = {
        key: value for key, value in environment.items()
        if not key.startswith(("UVICORN_", "ACCOUNTS_", "OPS_", "PYTEST_"))
        and key not in {"DATABASE_URL", "CONTENT_DIR", "PYTHONPATH"}
    }
    clean.update({
        "DATABASE_URL": "sqlite:///:memory:",
        "CONTENT_DIR": str(BACKEND / "content"),
        "APP_ENV": "verification", "ALLOW_DEMO_CONTENT": "true", "COOKIE_SECURE": "false",
        "ALLOWED_ORIGINS": LOAD_TARGET, "ACCOUNTS_ENABLED": "false",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": os.pathsep.join((str(BACKEND), str(ROOT / "scripts" / "ops"))),
    })
    return clean


def create_fresh_database(tools: PostgresTools, name: str, *, purpose: str) -> None:
    prefixes = {"recovery": "verify_recovery_source_", "load": "verify_load_"}
    if purpose not in prefixes or not re.fullmatch(prefixes[purpose] + r"[0-9a-f]{32}", name):
        raise OperationError("new_namespaced_verification_database_required")
    identifier(name)
    with tools.session("postgres") as admin:
        if admin.query(f"SELECT 1 FROM pg_database WHERE datname = '{name}';"):
            raise OperationError("verification_database_already_exists")
        # CREATE is the atomic second absence guard, including a racing creator.
        admin.query(f'CREATE DATABASE "{name}" WITH TEMPLATE template0;')
    with tools.session(name) as created:
        if created.query(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';"
        ) != ["0"]:
            raise OperationError("new_verification_database_not_empty")


def wait_for_postgres(environment: Mapping[str, str], seconds: int = 90) -> int:
    deadline = time.monotonic() + seconds
    tools = PostgresTools(environment=environment, timeout_seconds=3)
    while time.monotonic() < deadline:
        try:
            with tools.session("postgres") as admin:
                rows = admin.query("SHOW server_version_num;")
        except OperationError:
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            continue
        if len(rows) != 1 or not rows[0].isdigit() or int(rows[0]) // 10000 != 18:
            raise OperationError("verification_requires_postgres_18")
        return int(rows[0])
    raise OperationError("postgres_readiness_deadline_exceeded")


def client_versions(environment: Mapping[str, str]) -> dict[str, str]:
    found = {}
    for program in ("psql", "pg_dump", "pg_restore"):
        result = subprocess.run(
            [program, "--version"], env=dict(environment), check=False, timeout=10,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        match = re.fullmatch(
            rb"[a-z_]+ \(PostgreSQL\) ([0-9]+(?:\.[0-9]+)*)(?: [^\r\n]*)?\r?\n?",
            result.stdout[:1024],
        )
        if result.returncode or not match or match[1].split(b".")[0] != b"18":
            raise OperationError("verification_requires_postgres_18_clients")
        found[program] = match[1].decode("ascii")
    return found


def source_identity(expected_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise OperationError("explicit_checked_out_commit_required")
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT, check=False, timeout=10,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if result.returncode or result.stdout.strip() != expected_commit.encode("ascii"):
        raise OperationError("checked_out_commit_mismatch")
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT,
        check=False, timeout=10, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    if status.returncode or status.stdout:
        raise OperationError("checked_out_sources_not_clean")
    return {
        "checked_out_commit": expected_commit, "working_tree_clean": True,
        "migration_head": migration_head(),
        "migration_files_sha256": {
            path.relative_to(BACKEND).as_posix(): file_sha256(path)
            for path in sorted((BACKEND / "migrations").rglob("*.py"))
        },
    }


def content_inventory(directory: Path) -> dict[str, Any]:
    directory = private_directory(directory)
    names = ("profile.json", "lessons.json", "tasks.json")
    if not all((directory / name).is_file() for name in names):
        raise OperationError("expanded_course_package_missing")
    hashes = {name: file_sha256(directory / name) for name in names}
    content = load_content(directory)
    tasks = content.available_tasks(allow_demo_content=True)
    slots = {slot.number for slot in content.profile.slots}
    counts = Counter(task.slot for task in tasks)
    families = {slot: len({task.family_id for task in tasks if task.slot == slot})
                for slot in slots}
    if slots != set(range(1, 14)) or len(tasks) < 650 or any(
        counts[slot] < 50 or families[slot] < 5 for slot in slots
    ):
        raise OperationError("expanded_course_coverage_required")
    return {
        "file_sha256": hashes, "profile_id": content.profile.id,
        "profile_revision": content.profile.revision, "profile_status": content.profile.status,
        "issuable_tasks": len(tasks), "lessons": len(content.lessons),
        "tasks_per_slot": dict(sorted(counts.items())),
        "families_per_slot": dict(sorted(families.items())),
        "allow_demo_content": True, "independent_content_review_claimed": False,
    }


def stop_child(process: subprocess.Popen) -> dict[str, Any]:
    running, forced = process.poll() is None, False
    if running:
        if os.name == "posix":
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            forced = True
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
    return {"was_running": running, "forced_stop": forced, "exit_code": process.returncode}


def run_child(
    arguments: list[str], environment: Mapping[str, str], *, seconds: int,
    evidence: Path, output: Path | None = None,
) -> dict[str, Any]:
    require_absent_path(evidence)
    started = time.monotonic()
    result: dict[str, Any] = {"timeout_seconds": seconds, "timed_out": False, "exit_code": None}
    stream = None
    process = None
    try:
        if output is not None:
            require_absent_path(output)
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            stream = os.fdopen(descriptor, "wb")
        process = subprocess.Popen(
            arguments, cwd=BACKEND, env=dict(environment), stdin=subprocess.DEVNULL,
            stdout=stream if stream is not None else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=os.name == "posix",
        )
        try:
            result["exit_code"] = process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            result["timed_out"] = True
    finally:
        if process is not None:
            result["stop"] = stop_child(process)
            result["exit_code"] = process.returncode
        if stream is not None:
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_new_json(evidence, result)
    return result


def require_successful_child(result: Mapping[str, Any]) -> None:
    if result["timed_out"] or result["exit_code"] != 0:
        raise OperationError("verification_child_failed_or_timed_out")


def require_recovery_junit(path: Path) -> None:
    regular_file(path)
    if path.stat().st_size > 1_048_576:
        raise OperationError("recovery_junit_size_limit_exceeded")
    try:
        report = ElementTree.fromstring(path.read_bytes())
    except ElementTree.ParseError:
        raise OperationError("recovery_junit_invalid") from None
    cases = report.findall(".//testcase")
    if len(cases) != len(RECOVERY_TESTS) or {case.get("name") for case in cases} != {
        node.split("::")[1] for node in RECOVERY_TESTS
    } or any(case.find(tag) is not None for case in cases for tag in (
        "skipped", "failure", "error",
    )) or any(report.findall(".//" + tag) for tag in ("skipped", "failure", "error")):
        raise OperationError("both_live_recovery_tests_must_pass_without_skips")


def run_recovery(directory: Path, environment: Mapping[str, str]) -> None:
    temporary, junit = directory / "pytest-recovery", directory / "recovery.junit.xml"
    require_absent_path(temporary)
    require_absent_path(junit)
    env = child_environment(environment)
    env["OPS_RUN_POSTGRES_VERIFY"] = "1"
    result = run_child(
        [sys.executable, "-m", "pytest", *RECOVERY_TESTS, "-q", "--tb=no",
         "--show-capture=no", "-p", "no:cacheprovider", "-p", "verify_postgres",
         "-o", "junit_logging=no", "--basetemp", str(temporary), "--junitxml", str(junit)],
        env, seconds=480, evidence=directory / "recovery-process.json",
    )
    require_successful_child(result)
    require_recovery_junit(junit)
    for filename in ("postgres-restore-evidence.json", "full-postgres-restore-evidence.json"):
        if len(list(temporary.rglob(filename))) != 1:
            raise OperationError("live_recovery_evidence_missing")


def wait_for_api(process: subprocess.Popen, config: LoadConfig, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    transport = HttpTransport(config.target, namespace=config.namespace, timeout_seconds=2)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise OperationError("verification_api_exited_before_readiness")
        try:
            status, payload = transport.request("GET", config.route + "/health")
        except OperationError:
            status, payload = 0, None
        if status == 200 and payload == {"status": "ok"}:
            verify_empty_target(transport, config)
            return
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    raise OperationError("verification_api_readiness_deadline_exceeded")


def require_full_workload(report: Any, config: LoadConfig, actual_seconds: float) -> None:
    if not isinstance(report, dict) or report.get("conditions") != config.description():
        raise OperationError("workload_conditions_mismatch")
    flags = (
        "isolation_preflight_verified", "execution_complete", "workload_complete",
        "all_users_active_every_minute", "observed_client_thresholds_met",
        "full_control_scenario_completed",
    )
    counts = {
        "requests_dispatched": 18000, "requests_finished": 18000,
        "http_statuses_received": 18000, "http_responses_completed": 18000,
        "guest_users_created": 500, "users_with_completed_session": 500,
        "logical_users_touched": 500, "missed_schedule_slots": 0, "disabled_users": 0,
        "bank_exhaustion_responses": 0, "bank_exhausted_users": 0, "server_errors": 0,
    }
    if report.get("dry_run") is not False or any(report.get(flag) is not True for flag in flags):
        raise OperationError("full_useful_workload_not_completed")
    if any(type(report.get(key)) is not int or report[key] != value
           for key, value in counts.items()):
        raise OperationError("full_workload_counters_not_met")
    if report.get("active_logical_users_per_minute") != dict.fromkeys(map(str, range(10)), 500):
        raise OperationError("full_workload_minute_coverage_not_met")
    elapsed = report.get("elapsed_seconds_including_drain")
    if not isinstance(elapsed, (float, int)) or elapsed < 600 or actual_seconds < 600:
        raise OperationError("full_workload_duration_not_observed")


def durable_load_counts(tools: PostgresTools, database: str) -> dict[str, int]:
    verification_namespace(database)
    queries = {
        "guests": "SELECT count(*) FROM guests;",
        "attempts": "SELECT count(*) FROM attempts;",
        "idempotency_records": "SELECT count(*) FROM idempotency_records;",
        "completed_five_task_session_owners": (
            "SELECT count(DISTINCT guest_id) FROM learning_sessions "
            "WHERE status = 'completed' AND requested_length = 5 "
            "AND json_array_length(tasks_snapshot) = 5;"
        ),
    }
    result = {}
    with tools.session(database) as session:
        session.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        for name, query in queries.items():
            rows = session.query(query)
            if len(rows) != 1 or not rows[0].isdigit():
                raise OperationError("invalid_durable_workload_count")
            result[name] = int(rows[0])
        session.query("COMMIT;")
    return result


def run_workload(directory: Path, environment: Mapping[str, str], content_dir: Path, head: str):
    namespace = "verify_load_" + uuid4().hex
    config = LoadConfig(target=LOAD_TARGET, route="/api/v1", namespace=namespace)
    write_new_json(directory / "load-target.json", {
        "database": namespace, "conditions": config.description(), "automatic_cleanup": False,
    })
    inventory = content_inventory(content_dir)
    write_new_json(directory / "load-content.json", inventory)
    tools = PostgresTools(environment=environment, timeout_seconds=120)
    create_fresh_database(tools, namespace, purpose="load")
    env = child_environment(environment)
    env.update({
        "DATABASE_URL": f"postgresql+psycopg:///{namespace}?connect_timeout=10",
        "CONTENT_DIR": str(content_dir), "OPS_VERIFICATION_NAMESPACE": namespace,
        "OPS_LOAD_TARGET": config.target, "PGDATABASE": namespace,
    })
    migrated, process = False, None
    try:
        result = run_child(
            [sys.executable, "-m", "alembic", "upgrade", head], env, seconds=120,
            evidence=directory / "load-migration-process.json",
        )
        require_successful_child(result)
        migrated = True
        with tools.session(namespace) as session:
            if session.query("SELECT version_num FROM alembic_version;") != [head]:
                raise OperationError("load_database_migration_head_mismatch")
        # Refuse an occupied listener before launching; HTTP preflight also binds
        # the responding server to this fresh database's unguessable namespace.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 8001))
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
             "--port", "8001", "--workers", "1", "--no-access-log", "--log-level", "critical",
             "--timeout-graceful-shutdown", "15"],
            cwd=BACKEND, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=os.name == "posix",
        )
        wait_for_api(process, config)
        status, profile = HttpTransport(
            config.target, namespace=namespace, timeout_seconds=5,
        ).request("GET", "/api/v1/profile")
        if status != 200 or not isinstance(profile, dict) or any(
            profile.get(key) != inventory["profile_" + key] for key in ("id", "revision")
        ):
            raise OperationError("served_expanded_profile_mismatch")
        write_new_json(directory / "load-readiness.json", {
            "health_ready": True, "empty_namespace_verified": True,
            "expanded_profile_matches": True, "migration_head": head,
        })
        result = run_child(
            [sys.executable, str(ROOT / "scripts" / "ops" / "load_scenario.py"),
             "--target-route", "/api/v1", "--users", "500", "--rps", "30", "--seconds", "600",
             "--max-in-flight", "30", "--timeout-seconds", "5", "--confirm-load"],
            env, seconds=720, evidence=directory / "load-process.json",
            output=directory / "workload.json",
        )
        require_successful_child(result)
        report_path = directory / "workload.json"
        regular_file(report_path)
        if report_path.stat().st_size > 1_048_576:
            raise OperationError("workload_report_size_limit_exceeded")
        require_full_workload(
            json.loads(report_path.read_bytes()), config, result["elapsed_seconds"],
        )
        counts = durable_load_counts(tools, namespace)
        write_new_json(directory / "load-durable-counts.json", counts)
        if counts["guests"] != 500 or counts["completed_five_task_session_owners"] != 500 or (
            counts["attempts"] < 2500 or counts["idempotency_records"] < 3500
        ):
            raise OperationError("durable_workload_not_completed")
        if process.poll() is not None:
            raise OperationError("verification_api_exited_during_workload")
        if content_inventory(content_dir) != inventory:
            raise OperationError("expanded_content_changed_during_workload")
    finally:
        if process is not None:
            write_new_json(directory / "api-stop.json", stop_child(process))
        if migrated:
            # Persist the synthetic workload DB, even when a load threshold fails.
            # A stopped hosted runner's volume alone is not a durable CI artifact.
            backup = create_backup(
                tools, source=namespace, directory=directory / "load-backups", expected_head=head,
            )
            write_new_json(directory / "load-backup.json", backup)


def error_code(error: Exception) -> str:
    if isinstance(error, OperationError) and re.fullmatch(r"[a-z][a-z0-9_]{0,95}", str(error)):
        return str(error)
    return "verification_stage_failed"


def _interrupt(_signum, _frame):
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--content-dir", type=Path, default=BACKEND / "content" / "course")
    directory = None
    summary: dict[str, Any] = {
        "status": "failed", "stages": {}, "automatic_cleanup": False,
        "production_recovery_acceptance": False,
        "performance_acceptance": "requires_infrastructure_protocol_and_server_side_timings",
    }
    try:
        args = parser.parse_args(argv)
        directory = reserve_directory(args.artifacts_dir)
        if platform.system() != "Linux" or sys.prefix == sys.base_prefix:
            raise OperationError("linux_project_venv_required")
        signal.signal(signal.SIGTERM, _interrupt)
        identity = source_identity(args.expected_commit)
        write_new_json(directory / "run.json", {
            **identity, "started_at": datetime.now(UTC).isoformat(),
            "system": platform.system(), "machine": platform.machine(),
            "python": platform.python_version(), "cpu_count": os.cpu_count(),
            "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
            "packages": {name: version(name) for name in (
                "SQLAlchemy", "alembic", "psycopg", "pytest", "uvicorn",
            )},
        })
        environment = direct_environment(os.environ)
        write_new_json(directory / "postgres-versions.json", {
            "clients": client_versions(environment),
            "server_version_num": wait_for_postgres(environment),
        })
        for name, run in (
            ("recovery", lambda: run_recovery(directory, environment)),
            ("workload", lambda: run_workload(
                directory, environment, args.content_dir, identity["migration_head"],
            )),
        ):
            started = time.monotonic()
            print_json({"stage": name, "status": "started"})
            try:
                run()
                result = {"status": "passed"}
            except Exception as error:
                result = {"status": "failed", "code": error_code(error)}
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            summary["stages"][name] = result
            write_new_json(directory / (name + "-stage.json"), result)
            print_json({"stage": name, **result})
        if source_identity(args.expected_commit) != identity:
            raise OperationError("checked_out_sources_changed_during_verification")
        if all(stage["status"] == "passed" for stage in summary["stages"].values()):
            summary["status"] = "passed"
    except KeyboardInterrupt:
        summary["code"] = "verification_interrupted"
    except Exception as error:
        summary["code"] = error_code(error)
    finally:
        if directory is not None:
            write_new_json(directory / "summary.json", summary)
    print_json(summary)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
