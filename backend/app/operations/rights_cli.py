"""An explicit database URL from the environment, opened read-only for counts."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.operations.common import (
    OperationError,
    SafeArgumentParser,
    canonical_uuid,
    no_links,
    print_json,
    regular_file,
)
from app.operations.rights import deletion_plan, deletion_status


@contextmanager
def read_only_database(value: str):
    url = make_url(value)
    if url.get_backend_name() == "sqlite":
        if not url.database or not Path(url.database).is_absolute() or url.query:
            raise OperationError("existing_absolute_sqlite_file_required")
        path = no_links(Path(url.database))
        regular_file(path)
        engine = create_engine(
            "sqlite+pysqlite://", hide_parameters=True,
            creator=lambda: sqlite3.connect(
                path.as_uri() + "?mode=ro", uri=True, autocommit=False,
            ),
        )
    elif url.drivername in {"postgres", "postgresql", "postgresql+psycopg"}:
        engine = create_engine(
            url.set(drivername="postgresql+psycopg"), hide_parameters=True,
            connect_args={"connect_timeout": 10},
        )
    else:
        raise OperationError("unsupported_read_only_database")
    try:
        with engine.connect() as connection, connection.begin():
            if engine.dialect.name == "postgresql":
                connection.execute(text(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY",
                ))
                connection.execute(text("SET LOCAL statement_timeout = '30s'"))
            yield connection
    finally:
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = SafeArgumentParser(
        description="Read-only data-rights status and scoped impact counts.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status")
    status.add_argument("--dry-run", action="store_true")
    plan = commands.add_parser("plan")
    plan.add_argument("--account-id", required=True)
    plan.add_argument("--request-id", required=True)
    plan.add_argument("--dry-run", action="store_true")
    try:
        args = parser.parse_args(argv)
        if args.command == "plan":
            canonical_uuid(args.account_id)
            canonical_uuid(args.request_id)
        value = os.environ.get("OPS_DATABASE_URL")
        if not value:
            raise OperationError("explicit_ops_database_url_required")
        with read_only_database(value) as connection:
            now = datetime.now(UTC)
            result = (
                deletion_status(connection, now) if args.command == "status" else deletion_plan(
                    connection, account_id=args.account_id, request_id=args.request_id, now=now,
                )
            )
        print_json(result)
        return 0
    except OperationError as exc:
        print_json({"status": "refused", "code": str(exc)})
        return 2
    except (OSError, ValueError, SQLAlchemyError):
        print_json({"status": "failed", "code": "read_only_data_rights_query_failed"})
        return 2
