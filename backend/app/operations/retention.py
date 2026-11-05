"""Thirty-day managed-backup policy. Planning is the default and does not write."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.operations.backup import BUNDLE_PATTERN, read_bundle
from app.operations.common import (
    OperationError,
    file_sha256,
    json_bytes,
    no_links,
    private_directory,
    regular_file,
    sync_directory,
    utc,
)

RETENTION_DAYS = 30


def retention_plan(directory: Path, *, now: datetime | None = None) -> dict[str, Any]:
    root = private_directory(directory)
    instant = utc(now if now is not None else datetime.now(UTC))
    cutoff = instant - timedelta(days=RETENTION_DAYS)
    candidates, blocked, ignored = [], 0, 0
    if not root.exists():
        raise OperationError("backup_directory_not_found")
    for path in sorted(root.iterdir()):
        if not BUNDLE_PATTERN.fullmatch(path.name):
            ignored += 1
            continue
        try:
            manifest = read_bundle(path)
            if {item.name for item in path.iterdir()} != {
                "manifest.json", manifest["archive"]["filename"],
            }:
                raise OperationError("unrecognized_files_in_backup_bundle")
            created = utc(datetime.fromisoformat(manifest["created_at"]))
            if created > instant:
                raise OperationError("backup_timestamp_in_future")
            if created <= cutoff:
                candidates.append({
                    "backup_id": path.name, "archive_bytes": manifest["archive"]["bytes"],
                    "archive_sha256": manifest["archive"]["sha256"],
                    "manifest_sha256": file_sha256(path / "manifest.json"),
                })
        except (OperationError, OSError, ValueError):
            blocked += 1
    # Bind approval to the exact root, filenames and both file checksums, not a wildcard.
    scope = hashlib.sha256(json_bytes({"root": str(root), "candidates": candidates})).hexdigest()
    return {
        "dry_run": True, "retention_days": RETENTION_DAYS, "cutoff_at": cutoff.isoformat(),
        "candidates": candidates, "candidate_count": len(candidates),
        "candidate_bytes": sum(item["archive_bytes"] for item in candidates),
        "blocked_bundle_count": blocked, "unmanaged_entries_preserved": ignored,
        "deletion_scope_sha256": scope,
    }


def apply_retention(directory: Path, *, confirmed_scope: str) -> dict[str, Any]:
    """Operator-only destructive entry point; never called by timers or startup.

    A CLI token is a technical interlock, not user consent for an agent to delete data.
    Agents must obtain separate deletion-specific authorization before calling this.
    """
    plan = retention_plan(directory)
    if not confirmed_scope or confirmed_scope != plan["deletion_scope_sha256"]:
        raise OperationError("exact_deletion_scope_confirmation_required")
    if plan["blocked_bundle_count"]:
        raise OperationError("retention_blocked_by_unverified_bundle")
    root = private_directory(directory)
    for item in plan["candidates"]:
        bundle = no_links(root / item["backup_id"])
        archive = bundle / (item["backup_id"] + ".dump")
        manifest = bundle / "manifest.json"
        if {path.name for path in bundle.iterdir()} != {archive.name, manifest.name}:
            raise OperationError("retention_scope_changed")
        if (file_sha256(archive) != item["archive_sha256"]
                or file_sha256(manifest) != item["manifest_sha256"]):
            raise OperationError("retention_scope_changed")
        regular_file(archive)
        regular_file(manifest)
        # Deliberately no recursive deletion, glob deletion, symlink following or database SQL.
        archive.unlink()
        manifest.unlink()
        bundle.rmdir()
    sync_directory(root)
    return {"dry_run": False, "removed_bundle_count": plan["candidate_count"],
            "deletion_scope_sha256": plan["deletion_scope_sha256"]}
