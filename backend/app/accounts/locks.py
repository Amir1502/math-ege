"""Shared login mutation barriers, including deletion's credential-cleanup boundary."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.models import AuthRateLimit


def lock_auth_bucket(db: Session, key: str) -> AuthRateLimit:
    """Lock without consuming quota. Login and deletion acquire this before owner roots."""
    statement = select(AuthRateLimit).where(AuthRateLimit.key == key).with_for_update()
    bucket = db.scalar(statement.execution_options(populate_existing=True))
    if bucket is None:
        try:
            with db.begin_nested():
                db.add(AuthRateLimit(key=key, events=[]))
                db.flush()
        except IntegrityError:
            pass  # Another worker inserted the same lock row.
        bucket = db.scalars(statement.execution_options(populate_existing=True)).one()
    return bucket
