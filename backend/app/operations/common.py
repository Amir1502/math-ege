"""Small, fail-closed boundaries shared by operational commands."""

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID


class OperationError(Exception):
    """Only a fixed, non-sensitive error code may cross the CLI boundary."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # argparse normally repeats invalid arguments, which may include a URL secret.
        raise OperationError("invalid_arguments_use_help")


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise OperationError("timezone_aware_timestamp_required")
    return value.astimezone(UTC)


def identifier(value: str) -> str:
    # Never accept libpq connection strings, quoting, options, or truncatable identifiers.
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
        raise OperationError("invalid_database_identifier")
    return value


def revision(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,64}", value):
        raise OperationError("invalid_migration_revision")
    if value in {"head", "heads", "base"}:
        raise OperationError("explicit_migration_revision_required")
    return value


def canonical_uuid(value: str) -> str:
    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise OperationError("explicit_uuid_scope_required") from None
    if str(parsed) != value or parsed.int == 0:
        raise OperationError("explicit_uuid_scope_required")
    return value


def verification_namespace(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"verify_load_[0-9a-f]{32}", value):
        raise OperationError("isolated_load_namespace_required")
    return value


def restore_target(value: str, source: str, protected: tuple[str, ...] = ()) -> str:
    identifier(source)
    name = identifier(value)
    blocked = {"postgres", "template0", "template1", "math_ege", source}
    blocked.update(identifier(item) for item in protected)
    if not re.fullmatch(r"verify_restore_[a-z0-9][a-z0-9_]{0,47}", name) or name in blocked:
        raise OperationError("new_verification_database_required")
    return name


def no_links(path: Path) -> Path:
    """Reject symlinks/junctions in every existing component, including Windows."""
    path = path.absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise OperationError("linked_path_forbidden")
    return path


def private_directory(value: str | Path, *, create: bool = False) -> Path:
    path = Path(value)
    if not path.is_absolute() or path == Path(path.anchor):
        raise OperationError("explicit_absolute_directory_required")
    no_links(path)
    if create:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and not path.is_dir():
        raise OperationError("directory_required")
    return path.resolve()


def regular_file(path: Path) -> None:
    no_links(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise OperationError("private_regular_file_required")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode()


def file_sha256(path: Path) -> str:
    regular_file(path)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sync_directory(path: Path) -> None:
    # Windows does not expose directory fsync via os.open. Files are still fsynced.
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def publish_new_file(temporary: Path, destination: Path) -> None:
    """Atomically publish without replacement, including a racing destination."""
    if temporary.parent != destination.parent or destination.exists():
        raise OperationError("refusing_to_replace_file")
    no_links(temporary.parent)
    regular_file(temporary)
    try:
        # Unlike POSIX rename(), link() never replaces an existing destination.
        # Both names are in this run's private directory on the same filesystem.
        os.link(temporary, destination, follow_symlinks=False)
    except FileExistsError:
        raise OperationError("refusing_to_replace_file") from None
    sync_directory(destination.parent)
    # The durable final name now owns the same bytes; remove only our temporary name.
    temporary.unlink()
    sync_directory(destination.parent)


def write_new_json(path: Path, value: Any) -> None:
    no_links(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json_bytes(value))
        stream.flush()
        os.fsync(stream.fileno())


def print_json(value: Any) -> None:
    print(json_bytes(value).decode("ascii").rstrip())
