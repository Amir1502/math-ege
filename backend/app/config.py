"""Validated environment configuration, without working-directory dependence."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTENT_DIR = BACKEND_ROOT / "content"
DEFAULT_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"{name} must be 'true' or 'false'")
    return value.lower() == "true"


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'math_ege.sqlite3').as_posix()}"
    content_dir: Path = DEFAULT_CONTENT_DIR
    allow_demo_content: bool = False
    cookie_secure: bool = False
    allowed_origins: tuple[str, ...] = field(default_factory=lambda: DEFAULT_ORIGINS)
    environment: str = "development"
    guest_access_days: int = 180
    max_request_bytes: int = 16_384
    max_active_seconds: int = 86_400

    def __post_init__(self) -> None:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgres://")
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        if not url.startswith(("sqlite://", "sqlite+pysqlite://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL with psycopg")
        object.__setattr__(self, "database_url", url)
        object.__setattr__(self, "content_dir", Path(self.content_dir).resolve())
        if not self.allowed_origins:
            raise ValueError("ALLOWED_ORIGINS cannot be empty")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("ALLOWED_ORIGINS must contain exact origins without paths")
            _ = parsed.port
        requires_secure = self.environment == "production" or any(
            origin.startswith("https://") for origin in self.allowed_origins
        )
        if requires_secure and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production or with HTTPS origins")
        if not 1 <= self.guest_access_days <= 365:
            raise ValueError("GUEST_ACCESS_DAYS must be between 1 and 365")
        if not 512 <= self.max_request_bytes <= 1_048_576:
            raise ValueError("MAX_REQUEST_BYTES must be between 512 and 1048576")
        if not 1 <= self.max_active_seconds <= 86_400:
            raise ValueError("MAX_ACTIVE_SECONDS must be between 1 and 86400")

    @property
    def cookie_name(self) -> str:
        return "math_ege_guest"

    @classmethod
    def from_env(cls) -> "Settings":
        defaults = cls()
        environment = os.getenv("APP_ENV", "development")
        origins = tuple(
            value.strip()
            for value in os.getenv("ALLOWED_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",")
            if value.strip()
        )
        secure_default = environment == "production" or any(
            origin.startswith("https://") for origin in origins
        )
        return cls(
            database_url=os.getenv("DATABASE_URL", defaults.database_url),
            content_dir=Path(os.getenv("CONTENT_DIR", str(DEFAULT_CONTENT_DIR))),
            allow_demo_content=_boolean("ALLOW_DEMO_CONTENT", False),
            cookie_secure=_boolean("COOKIE_SECURE", secure_default),
            allowed_origins=origins,
            environment=environment,
            guest_access_days=int(os.getenv("GUEST_ACCESS_DAYS", "180")),
            max_request_bytes=int(os.getenv("MAX_REQUEST_BYTES", "16384")),
            max_active_seconds=int(os.getenv("MAX_ACTIVE_SECONDS", "86400")),
        )
