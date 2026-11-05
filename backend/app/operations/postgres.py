"""Binary-safe local/Docker PostgreSQL clients; no shell or secret-bearing argv."""

import os
import re
import subprocess
import time
from collections.abc import Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from queue import Empty, Full, Queue
from threading import Event, Thread
from typing import BinaryIO
from uuid import uuid4

from app.operations.common import OperationError, identifier

_CONNECTION_ENV = (
    "PGHOST", "PGPORT", "PGUSER", "PGPASSFILE", "PGSSLMODE", "PGSSLROOTCERT",
)
_CONTROLLED_ENV = {
    "PGCLIENTENCODING": "UTF8", "PGAPPNAME": "math_ege_operations",
    "PGCONNECT_TIMEOUT": "10", "PG_COLOR": "never", "PSQL_PAGER": "", "PAGER": "",
}
# libpq treats an empty PGSERVICE/PGSERVICEFILE as present, then fails opening the
# empty service file before any connection attempt. Ambient PG* values are dropped
# by command(); overrides that must be neutralised are absent, never set to "".


@dataclass(frozen=True)
class PostgresTools:
    container: str | None = None
    timeout_seconds: int = 3600
    environment: Mapping[str, str] = field(default_factory=lambda: dict(os.environ), repr=False)

    def __post_init__(self) -> None:
        if self.container is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", self.container,
        ):
            raise OperationError("invalid_postgres_container")
        if type(self.timeout_seconds) is not int or not 1 <= self.timeout_seconds <= 14_400:
            raise OperationError("invalid_operation_timeout")
        if not self.environment.get("PGUSER"):
            raise OperationError("explicit_pguser_required")

    def command(
        self, program: str, database: str, arguments: tuple[str, ...] = (),
    ) -> tuple[list[str], dict[str, str]]:
        if program not in {"psql", "pg_dump", "pg_restore"}:
            raise OperationError("postgres_program_not_allowed")
        identifier(database)
        env = {key: value for key, value in self.environment.items() if not key.startswith("PG")}
        for name in _CONNECTION_ENV:
            if name in self.environment:
                env[name] = self.environment[name]
        env.update(_CONTROLLED_ENV)
        env["PGDATABASE"] = database
        argv = []
        if self.container is not None:
            argv = ["docker", "exec", "--interactive"]
            # `--env NAME` copies the value from the Docker client's environment.
            # Values, including password-file paths, never become command arguments.
            for name in (*_CONNECTION_ENV, *_CONTROLLED_ENV, "PGDATABASE"):
                if name in env:
                    argv.extend(("--env", name))
            argv.append(self.container)
        return [*argv, program, *arguments], env

    def transfer(
        self, program: str, database: str, arguments: tuple[str, ...], *,
        source: BinaryIO | None = None, destination: BinaryIO | None = None,
    ) -> None:
        argv, env = self.command(program, database, arguments)
        diagnostics = Event()
        try:
            with subprocess.Popen(
                argv, env=env, stdin=source if source is not None else subprocess.DEVNULL,
                stdout=destination if destination is not None else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            ) as process:
                assert process.stderr is not None

                def discard_diagnostics() -> None:
                    try:
                        # Never accumulate unbounded stderr or persist failing COPY row values.
                        while process.stderr.read(16_384):
                            diagnostics.set()
                    except OSError:
                        diagnostics.set()

                reader = Thread(target=discard_diagnostics, name="ops-pg-stderr", daemon=True)
                reader.start()
                try:
                    returncode = process.wait(timeout=self.timeout_seconds)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)
                    reader.join(timeout=5)
                if reader.is_alive():
                    raise OperationError("postgres_diagnostics_reader_timed_out")
        except (OSError, subprocess.TimeoutExpired):
            raise OperationError("postgres_client_failed_or_timed_out") from None
        if returncode:
            # stderr can contain connection secrets or failing COPY row values.
            raise OperationError("postgres_client_failed")
        if diagnostics.is_set():
            raise OperationError("postgres_client_reported_diagnostics")

    def session(self, database: str) -> "PsqlSession":
        return PsqlSession(self, database)


class PsqlSession:
    """Keep an exported snapshot alive while pg_dump uses a second connection.

    A bounded reader thread makes pipe deadlines work on Windows as well as POSIX.
    Only fixed SQL, validated identifiers, and server-produced digests use this channel.
    """

    def __init__(self, tools: PostgresTools, database: str) -> None:
        self.tools, self.database = tools, identifier(database)
        self._lines: Queue[str | None] = Queue(maxsize=1024)
        self._stop = Event()
        self._process: subprocess.Popen[str] | None = None
        self._reader: Thread | None = None

    def __enter__(self) -> "PsqlSession":
        argv, env = self.tools.command("psql", self.database, (
            "--no-psqlrc", "--no-password", "--quiet", "--tuples-only", "--no-align",
            "--set=ON_ERROR_STOP=1", "--pset=pager=off", "--file=-",
        ))
        try:
            self._process = subprocess.Popen(
                argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            )
        except OSError:
            raise OperationError("postgres_client_unavailable") from None
        self._reader = Thread(target=self._read, name="ops-psql-reader", daemon=True)
        self._reader.start()
        try:
            self.query(
                "SET client_min_messages TO ERROR; SET timezone TO 'UTC'; "
                "SET datestyle TO 'ISO, YMD'; SET extra_float_digits TO 3; "
                "SET bytea_output TO 'hex'; SET row_security TO off; "
                "SET lock_timeout TO '5s'; "
                f"SET statement_timeout TO '{self.tools.timeout_seconds}s'; "
                "SET idle_in_transaction_session_timeout TO '4h';"
            )
            if self.query("SELECT current_database();") != [self.database]:
                raise OperationError("postgres_database_identity_mismatch")
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def _put(self, line: str | None) -> None:
        while not self._stop.is_set():
            try:
                self._lines.put(line, timeout=0.1)
                return
            except Full:
                continue

    def _read(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while not self._stop.is_set():
                line = self._process.stdout.readline(4097)
                if not line or len(line) > 4096:
                    break
                self._put(line.rstrip("\r\n"))
        except (OSError, UnicodeError):
            pass
        finally:
            self._put(None)

    def lines(self, sql: str) -> Iterator[str]:
        if self._process is None or self._process.stdin is None:
            raise OperationError("postgres_session_not_open")
        marker = "ops_end_" + uuid4().hex
        deadline = time.monotonic() + self.tools.timeout_seconds
        try:
            self._process.stdin.write(sql + "\n\\echo " + marker + "\n")
            self._process.stdin.flush()
        except (OSError, ValueError):
            raise OperationError("postgres_query_failed") from None
        while True:
            try:
                line = self._lines.get(timeout=max(0.001, deadline - time.monotonic()))
            except Empty:
                raise OperationError("postgres_query_timed_out") from None
            if line is None:
                raise OperationError("postgres_query_failed")
            if line == marker:
                return
            if time.monotonic() >= deadline:
                raise OperationError("postgres_query_timed_out")
            if line:
                yield line

    def query(self, sql: str) -> list[str]:
        values = []
        for line in self.lines(sql):
            if len(values) >= 1024:
                raise OperationError("postgres_metadata_limit_exceeded")
            values.append(line)
        return values

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._process is not None:
            if self._process.stdin is not None:
                with suppress(OSError):
                    self._process.stdin.close()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
            if self._reader is not None:
                self._reader.join(timeout=5)
            if self._process.stdout is not None:
                self._process.stdout.close()
