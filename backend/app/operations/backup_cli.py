"""Command dispatch kept separate from database/archive implementations."""

import os
from pathlib import Path

from app.operations.backup import create_backup, read_bundle, restore_backup, validate_inventory
from app.operations.common import (
    OperationError,
    SafeArgumentParser,
    identifier,
    print_json,
    private_directory,
    restore_target,
    revision,
)
from app.operations.postgres import PostgresTools
from app.operations.retention import apply_retention, retention_plan


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(description="PostgreSQL backup/restore and explicit retention.")
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser(
        "backup", help="Create a new archive, never replace an existing one",
    )
    backup.add_argument("--expected-head", required=True)
    backup.add_argument("--dry-run", action="store_true")
    restore = commands.add_parser(
        "restore", help="Restore only into a new verify_restore_* database",
    )
    restore.add_argument("--bundle", type=Path, required=True)
    restore.add_argument("--target-database", required=True)
    restore.add_argument("--expected-head", required=True)
    restore_mode = restore.add_mutually_exclusive_group()
    restore_mode.add_argument("--dry-run", action="store_true")
    restore_mode.add_argument("--confirm-restore", action="store_true")
    retention = commands.add_parser("retention", help="Default: read-only 30-day retention plan")
    mode = retention.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    retention.add_argument("--confirm-delete-scope")
    try:
        args = parser.parse_args(argv)
        if args.command == "retention":
            directory = _directory()
            if args.confirm_delete_scope and not args.apply:
                raise OperationError("apply_flag_required_for_retention")
            result = (
                apply_retention(directory, confirmed_scope=args.confirm_delete_scope or "")
                if args.apply else retention_plan(directory)
            )
        else:
            source = identifier(os.environ.get("OPS_SOURCE_DATABASE", ""))
            expected_head = revision(args.expected_head)
            tools = PostgresTools(container=os.environ.get("OPS_PG_CONTAINER") or None)
            if args.command == "backup":
                directory = _directory()
                result = (
                    {"dry_run": True, "operation": "backup", "migration_head": expected_head,
                     "database_contacted": False, "files_created": 0}
                    if args.dry_run else create_backup(
                        tools, source=source, directory=directory, expected_head=expected_head,
                    )
                )
            else:
                protected = tuple(filter(
                    None, os.environ.get("OPS_PROTECTED_DATABASES", "").split(","),
                ))
                target = restore_target(args.target_database, source, protected)
                manifest = read_bundle(args.bundle)
                restore_target(target, manifest["source_database"], protected)
                validate_inventory(manifest["inventory"], expected_head)
                result = (
                    restore_backup(
                        tools, bundle=args.bundle, target=target, source=source,
                        protected=protected, expected_head=expected_head,
                    ) if args.confirm_restore else {
                        "dry_run": True, "operation": "restore", "target_database": target,
                        "archive_checksum_verified": True, "database_contacted": False,
                        "target_absence_checked": False,
                    }
                )
        print_json(result)
        return 0
    except OperationError as exc:
        print_json({"status": "refused", "code": str(exc)})
        return 2
    except (OSError, ValueError, TypeError):
        print_json({"status": "failed", "code": "operational_io_or_configuration_error"})
        return 2


def _directory() -> Path:
    value = os.environ.get("OPS_BACKUP_DIR")
    if not value:
        raise OperationError("explicit_backup_directory_required")
    return private_directory(value)
