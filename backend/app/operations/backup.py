"""Consistent PostgreSQL archives and verification into a newly created database."""

import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.operations.common import (
    OperationError,
    file_sha256,
    identifier,
    no_links,
    private_directory,
    publish_new_file,
    regular_file,
    restore_target,
    revision,
    sync_directory,
    utc,
    write_new_json,
)
from app.operations.postgres import PostgresTools, PsqlSession

CORE_TABLES = frozenset({
    "alembic_version", "guests", "learning_sessions", "attempts", "seen_tasks",
    "idempotency_records",
})
BUNDLE_PATTERN = re.compile(r"math_ege_(\d{8}T\d{6}Z)_([0-9a-f]{32})")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
MANIFEST_VERSION = 1


def export_inventory(session: PsqlSession, expected_head: str) -> dict[str, Any]:
    """Only row hashes leave PostgreSQL; raw users, answers and snapshots do not."""
    expected_head = revision(expected_head)
    extra_schemas = session.query(
        "SELECT nspname FROM pg_catalog.pg_namespace "
        "WHERE nspname NOT LIKE 'pg_%' AND nspname NOT IN ('public', 'information_schema');"
    )
    if extra_schemas:
        raise OperationError("unsupported_nonpublic_schema")
    tables = session.query(
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public' "
        'ORDER BY tablename COLLATE "C";'
    )
    if len(tables) > 256 or not set(tables) >= CORE_TABLES:
        raise OperationError("required_core_tables_missing_or_unbounded")
    for table in tables:
        identifier(table)
    heads = session.query('SELECT version_num FROM public.alembic_version ORDER BY version_num;')
    if heads != [expected_head]:
        raise OperationError("migration_head_mismatch")
    exported = {}
    for table in tables:
        digest, count = hashlib.sha256(), 0
        # Deterministic multiset of complete rows includes all immutable content and results.
        # Sorting hashes avoids collation/primary-key assumptions, including composite keys.
        sql = (
            "SELECT row_hash FROM (SELECT "
            "encode(sha256(convert_to(row_to_json(t)::text, 'UTF8')), 'hex') AS row_hash "
            f'FROM public."{table}" AS t) AS hashed ORDER BY row_hash COLLATE "C";'
        )
        for row_hash in session.lines(sql):
            if not HASH_PATTERN.fullmatch(row_hash):
                raise OperationError("invalid_source_fingerprint")
            digest.update(row_hash.encode("ascii") + b"\n")
            count += 1
        exported[table] = {"rows": count, "sha256": digest.hexdigest()}
    return {
        "migration_heads": heads, "tables": exported, "algorithm": "sha256-sorted-row-sha256-v1",
    }


def validate_inventory(value: Any, expected_head: str | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"migration_heads", "tables", "algorithm"}:
        raise OperationError("invalid_inventory")
    if value["algorithm"] != "sha256-sorted-row-sha256-v1":
        raise OperationError("unsupported_inventory_algorithm")
    heads, tables = value["migration_heads"], value["tables"]
    if not isinstance(heads, list) or len(heads) != 1:
        raise OperationError("invalid_inventory_migrations")
    revision(heads[0])
    if expected_head is not None and heads != [revision(expected_head)]:
        raise OperationError("migration_head_mismatch")
    if not isinstance(tables, dict) or len(tables) > 256 or not tables.keys() >= CORE_TABLES:
        raise OperationError("invalid_inventory_tables")
    for name, metadata in tables.items():
        identifier(name)
        if not isinstance(metadata, dict) or set(metadata) != {"rows", "sha256"}:
            raise OperationError("invalid_table_fingerprint")
        if type(metadata["rows"]) is not int or not 0 <= metadata["rows"] <= 2**63 - 1:
            raise OperationError("invalid_table_count")
        checksum = metadata["sha256"]
        if not isinstance(checksum, str) or not HASH_PATTERN.fullmatch(checksum):
            raise OperationError("invalid_table_fingerprint")
    return value


def validate_manifest(value: Any, bundle_name: str) -> dict[str, Any]:
    expected_keys = {
        "version", "backup_id", "created_at", "source_database", "server_version_num",
        "archive", "inventory",
    }
    match = BUNDLE_PATTERN.fullmatch(bundle_name)
    if not match or not isinstance(value, dict) or set(value) != expected_keys:
        raise OperationError("invalid_backup_manifest")
    if type(value["version"]) is not int or value["version"] != MANIFEST_VERSION:
        raise OperationError("unsupported_manifest_version")
    if value["backup_id"] != bundle_name:
        raise OperationError("backup_identity_mismatch")
    try:
        created = utc(datetime.fromisoformat(value["created_at"]))
    except (ValueError, TypeError):
        raise OperationError("invalid_backup_timestamp") from None
    if created.strftime("%Y%m%dT%H%M%SZ") != match[1]:
        raise OperationError("backup_timestamp_mismatch")
    identifier(value["source_database"])
    if type(value["server_version_num"]) is not int or value["server_version_num"] < 130000:
        raise OperationError("unsupported_postgres_version")
    archive = value["archive"]
    if not isinstance(archive, dict) or set(archive) != {"filename", "bytes", "sha256"}:
        raise OperationError("invalid_archive_metadata")
    if archive["filename"] != bundle_name + ".dump":
        raise OperationError("archive_path_not_owned")
    if type(archive["bytes"]) is not int or archive["bytes"] < 5:
        raise OperationError("invalid_archive_size")
    if not isinstance(archive["sha256"], str) or not HASH_PATTERN.fullmatch(archive["sha256"]):
        raise OperationError("invalid_archive_checksum")
    validate_inventory(value["inventory"])
    return value


def read_bundle(bundle: Path, *, verify_archive: bool = True) -> dict[str, Any]:
    bundle = private_directory(bundle)
    if not bundle.is_dir():
        raise OperationError("backup_bundle_not_found")
    manifest_file = bundle / "manifest.json"
    regular_file(manifest_file)
    if manifest_file.stat().st_size > 262_144:
        raise OperationError("manifest_size_limit_exceeded")
    try:
        value = json.loads(manifest_file.read_bytes())
    except (ValueError, UnicodeError):
        raise OperationError("invalid_backup_manifest") from None
    manifest = validate_manifest(value, bundle.name)
    archive = bundle / manifest["archive"]["filename"]
    regular_file(archive)
    if archive.stat().st_size != manifest["archive"]["bytes"]:
        raise OperationError("archive_size_mismatch")
    if verify_archive:
        if file_sha256(archive) != manifest["archive"]["sha256"]:
            raise OperationError("archive_checksum_mismatch")
        with archive.open("rb") as stream:
            if stream.read(5) != b"PGDMP":
                raise OperationError("custom_postgres_archive_required")
    return manifest


def _server_version(session: PsqlSession) -> int:
    result = session.query("SHOW server_version_num;")
    if len(result) != 1 or not result[0].isdigit() or int(result[0]) < 130000:
        raise OperationError("unsupported_postgres_version")
    return int(result[0])


def create_backup(
    tools: PostgresTools, *, source: str, directory: Path, expected_head: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    source, expected_head = identifier(source), revision(expected_head)
    created = utc(now if now is not None else datetime.now(UTC))
    directory = private_directory(directory, create=True)
    backup_id = f"math_ege_{created.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex}"
    bundle = directory / backup_id
    # The parent is never emptied; each run reserves its own 0700 directory exclusively.
    bundle.mkdir(mode=0o700, exist_ok=False)
    sync_directory(directory)
    dump = bundle / (backup_id + ".dump")
    temporary = dump.with_suffix(".dump.partial")
    with tools.session(source) as session:
        session.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        server_version = _server_version(session)
        snapshot_rows = session.query("SELECT pg_export_snapshot();")
        if len(snapshot_rows) != 1 or not re.fullmatch(r"[A-Fa-f0-9-]{1,128}", snapshot_rows[0]):
            raise OperationError("invalid_exported_snapshot")
        inventory = export_inventory(session, expected_head)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            tools.transfer("pg_dump", source, (
                "--format=custom", "--no-password", "--lock-wait-timeout=5000",
                "--snapshot=" + snapshot_rows[0],
            ), destination=output)
            output.flush()
            os.fsync(output.fileno())
        # The exporting transaction remains alive until pg_dump has finished.
        session.query("COMMIT;")
    if temporary.stat().st_size < 5:
        raise OperationError("empty_backup")
    with temporary.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise OperationError("custom_postgres_archive_required")
    manifest = {
        "version": MANIFEST_VERSION, "backup_id": backup_id, "created_at": created.isoformat(),
        "source_database": source, "server_version_num": server_version,
        "archive": {
            "filename": dump.name, "bytes": temporary.stat().st_size,
            "sha256": file_sha256(temporary),
        },
        "inventory": inventory,
    }
    validate_manifest(manifest, backup_id)
    publish_new_file(temporary, dump)
    pending_manifest = bundle / "manifest.json.partial"
    write_new_json(pending_manifest, manifest)
    # Presence of this final manifest is the commit marker consumed by retention/restore.
    publish_new_file(pending_manifest, bundle / "manifest.json")
    return {
        "status": "backup_created", "backup_id": backup_id,
        "archive_bytes": manifest["archive"]["bytes"],
        "archive_sha256": manifest["archive"]["sha256"], "created_at": created.isoformat(),
        "restoration_verified": False,
    }


def restore_backup(
    tools: PostgresTools, *, bundle: Path, target: str, expected_head: str,
    source: str, protected: tuple[str, ...] = (),
) -> dict[str, Any]:
    target = restore_target(target, source, protected)
    manifest = read_bundle(bundle)
    restore_target(target, manifest["source_database"], protected)
    validate_inventory(manifest["inventory"], expected_head)
    started = time.monotonic()
    # No `--create`: that flag would use the SOURCE database name embedded in the archive.
    with tools.session("postgres") as admin:
        if admin.query(f"SELECT 1 FROM pg_database WHERE datname = '{target}';"):
            raise OperationError("restore_target_already_exists")
        if _server_version(admin) // 10000 != manifest["server_version_num"] // 10000:
            raise OperationError("restore_verification_requires_same_postgres_major")
        # CREATE itself arbitrates a racing creator; there is no destructive recovery path.
        admin.query(f'CREATE DATABASE "{target}" WITH TEMPLATE template0;')
    with tools.session(target) as empty:
        objects = empty.query(
            "SELECT count(*) FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema';"
        )
        if objects != ["0"]:
            raise OperationError("restore_target_not_empty")
    archive = no_links(bundle / manifest["archive"]["filename"])
    # Recheck immediately before use. An unsuccessful target and all evidence are preserved.
    if file_sha256(archive) != manifest["archive"]["sha256"]:
        raise OperationError("archive_checksum_mismatch")
    with archive.open("rb") as stream:
        tools.transfer("pg_restore", target, (
            "--dbname=" + target, "--format=custom", "--no-password", "--exit-on-error",
            "--single-transaction", "--no-owner", "--no-privileges", "--no-tablespaces",
        ), source=stream)
    with tools.session(target) as restored:
        restored.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;")
        actual = export_inventory(restored, expected_head)
        restored.query("COMMIT;")
    if actual != manifest["inventory"]:
        raise OperationError("restored_history_or_snapshot_mismatch")
    return {
        "status": "restore_verified", "backup_id": manifest["backup_id"],
        "target_database": target, "migration_heads": actual["migration_heads"],
        "table_counts": {name: item["rows"] for name, item in actual["tables"].items()},
        "all_row_and_snapshot_checksums_match": True,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "rpo_target_hours": 24, "rto_target_hours": 4,
        "production_recovery_acceptance": False,
    }
