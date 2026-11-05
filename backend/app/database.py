"""Short, explicit transactions with database-backed concurrency controls."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.models import Base


class Database:
    def __init__(self, settings: Settings) -> None:
        options: dict[str, Any] = {"pool_pre_ping": True}
        sqlite = settings.database_url.startswith("sqlite")
        if sqlite:
            options["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if settings.database_url.rstrip("/").endswith(":memory:"):
                options["poolclass"] = StaticPool
        self.engine: Engine = create_engine(settings.database_url, **options)
        if sqlite:
            event.listen(self.engine, "connect", self._sqlite_connect)
            event.listen(self.engine, "begin", self._sqlite_begin)

    @staticmethod
    def _sqlite_connect(connection: Any, _: Any) -> None:
        # SQLAlchemy owns BEGIN, including reads. This avoids pysqlite's legacy
        # SELECT-outside-transaction behavior on Python 3.13.
        connection.isolation_level = None
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    @staticmethod
    def _sqlite_begin(connection: Connection) -> None:
        # SQLite has no row locks. Acquire its write reservation before reading
        # idempotency, revisions, assistance or selection state. PostgreSQL uses
        # the guest row lock in services.py, so different guests can proceed.
        statement = (
            "BEGIN IMMEDIATE" if connection.get_execution_options().get("write") else "BEGIN"
        )
        connection.exec_driver_sql(statement)

    @contextmanager
    def transaction(self, *, write: bool = False) -> Iterator[Session]:
        with self.engine.connect() as connection:
            connection = connection.execution_options(write=write)
            with connection.begin(), Session(
                bind=connection, expire_on_commit=False, join_transaction_mode="rollback_only"
            ) as session:
                yield session
                session.flush()

    def create_schema_for_tests(self) -> None:
        """Explicit test helper. Production schema changes go through Alembic."""
        Base.metadata.create_all(self.engine)

    def check(self) -> None:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))

    def dispose(self) -> None:
        self.engine.dispose()
