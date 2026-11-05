"""Opt-in localhost browser factory; private mail/clock files, never test HTTP routes."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

from cryptography.fernet import Fernet

from app.accounts.config import AccountSettings
from app.accounts.service import AccountService
from app.config import Settings
from app.main import create_app

ORIGIN = "http://127.0.0.1:5193"


def _root() -> Path:
    value = os.environ.get("IDENTITY_BROWSER_RUN_ROOT")
    if not value or os.environ.get("APP_ENV") != "test":
        raise ValueError("The identity browser factory requires an isolated test runtime")
    root = Path(value).resolve()
    temporary = Path(os.environ["LOCALAPPDATA"], "Temp", "opencode").resolve()
    if root == temporary or not root.is_relative_to(temporary):
        raise ValueError("Identity browser files must be in a new approved temporary directory")
    return root


class PrivateMailbox:
    def __init__(self, root: Path) -> None:
        self.path = root / "mailbox.jsonl"
        self.lock = Lock()
        # Refuse to overwrite a mailbox from any earlier run.
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)

    def send_login_link(self, email: str, link: str, expires_at: datetime) -> None:
        if not email.endswith(".invalid") or not link.startswith(f"{ORIGIN}/account#token="):
            raise ValueError("Only synthetic local browser mail is permitted")
        message = {"email": email, "link": link, "expires_at": expires_at.isoformat()}
        with self.lock, self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(message) + "\n")


def create_identity_app():
    root = _root()
    config = Settings.from_env()
    database_url = f"sqlite:///{(root / 'identity.sqlite3').as_posix()}"
    if config.database_url != database_url or config.allowed_origins != (ORIGIN,):
        raise ValueError("The browser factory must use its isolated database and exact origin")

    def clock() -> datetime:
        offset = json.loads((root / "clock.json").read_text(encoding="utf-8"))["offset_seconds"]
        if type(offset) is not int or not 0 <= offset <= 3600:
            raise ValueError("The private test clock offset must be between zero and one hour")
        return datetime.now(UTC) + timedelta(seconds=offset)

    application = create_app(config, clock=clock)
    application.state.accounts = AccountService(
        application.state.service,
        config=AccountSettings(
            enabled=True, policy_approved=True, policy_version="identity-browser-1",
            policy_url=f"{ORIGIN}/privacy-test.txt", public_origin=ORIGIN,
            mfa_encryption_key=Fernet.generate_key().decode("ascii"),
        ),
        mail_sender=PrivateMailbox(root),
    )
    return application
