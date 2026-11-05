"""One authenticated root lock, with explicit scopes for immutable legacy owners.

Callers must use Database.transaction(write=True) before resolving for a write.
Pass the injected clock to recheck deadlines after all authorization locks.
Never pass a client-supplied UUID as an authenticated principal.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import AccessSession, Account, GuestClaim
from app.accounts.tokens import token_digest
from app.errors import ApiError
from app.models import Guest


def _unauthorized() -> ApiError:
    return ApiError(401, "guest_required", "Сеанс отсутствует или истёк. Начните новый вход.")


def _check_session(
    account: Account | None, access: AccessSession | None, root: Guest | None,
    token: str | None, now: datetime,
) -> None:
    """Revalidate already locked/refreshed state after any later authorization lock."""
    digest = token_digest(token)
    if (
        digest is None or root is None or account is None or access is None
        or access.token_digest != digest or access.account_id != account.id
        or account.root_guest_id != root.id or account.email_verified_at is None
        or access.revoked_at is not None or access.expires_at <= now
    ):
        raise _unauthorized()


def resolve_guest(
    db: Session, token: str | None, now: datetime, write: bool = False,
    *, clock: Callable[[], datetime] | None = None,
) -> Guest:
    digest = token_digest(token)
    if digest is None:
        raise _unauthorized()
    access = db.scalar(select(AccessSession).where(AccessSession.token_digest == digest))
    if access is not None:
        account = db.get(Account, access.account_id)
        if account is None:
            raise _unauthorized()
        statement = select(Guest).where(Guest.id == account.root_guest_id)
        if write:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        root = db.scalar(statement)
        # Root first, then account/access: even a last_seen UPDATE can otherwise
        # wait on an access-row lock after the authorization timestamp was sampled.
        account_statement = select(Account).where(Account.id == account.id)
        access_statement = select(AccessSession).where(AccessSession.token_digest == digest)
        if write:
            account_statement = account_statement.with_for_update()
            access_statement = access_statement.with_for_update()
        account = db.scalar(account_statement.execution_options(populate_existing=True))
        access = db.scalar(access_statement.execution_options(populate_existing=True))
        now = clock() if clock is not None else now
        _check_session(account, access, root, token, now)
        if write:
            root.last_seen_at = now
            access.last_seen_at = now
        return root

    statement = select(Guest).where(Guest.token_digest == digest)
    if write:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    guest = db.scalar(statement)
    claim = db.get(GuestClaim, guest.id) if guest is not None else None
    now = clock() if clock is not None else now
    if (
        guest is None or guest.expires_at <= now or guest.token_digest != digest
        or claim is not None
    ):
        raise _unauthorized()
    if write:
        guest.last_seen_at = now
    return guest


def owner_ids(db: Session, guest: Guest) -> list[str]:
    """Scope of a resolved principal. Only an account root expands its scope."""
    account_id = db.scalar(select(Account.id).where(Account.root_guest_id == guest.id))
    if account_id is None:
        return [guest.id]
    return sorted({guest.id, *db.scalars(
        select(GuestClaim.guest_id).where(GuestClaim.account_id == account_id)
    )})


def root_owner_id(db: Session, guest_id: str) -> str:
    """Map an internal historic owner to its write-lock root; this is not auth."""
    return db.scalar(
        select(Account.root_guest_id).join(GuestClaim, GuestClaim.account_id == Account.id)
        .where(GuestClaim.guest_id == guest_id)
    ) or guest_id


def account_session(
    db: Session, token: str | None, now: datetime, *, write: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> tuple[Account, AccessSession, Guest]:
    guest = resolve_guest(db, token, now, write=write, clock=clock)
    access = db.scalar(select(AccessSession).where(
        AccessSession.token_digest == token_digest(token),
    ))
    if access is None:
        raise ApiError(401, "account_required", "Войдите в подтверждённый аккаунт.")
    account = db.scalar(
        select(Account).where(Account.id == access.account_id)
        .execution_options(populate_existing=True)
    )
    _check_session(account, access, guest, token, clock() if clock is not None else now)
    return account, access, guest
