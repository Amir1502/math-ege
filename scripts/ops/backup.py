"""Run with the project's virtualenv Python; PostgreSQL clients may run in Docker."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.operations.backup_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
