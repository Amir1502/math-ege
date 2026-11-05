"""Use backend/.venv Python. The command only reads explicitly selected databases."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.operations.rights_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
