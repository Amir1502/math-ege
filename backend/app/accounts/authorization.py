"""Shared server-side role/MFA gate for editorial routes and transactions."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.mfa import mfa_until
from app.accounts.models import TotpCredential
from app.accounts.principals import _check_session, account_session
from app.errors import ApiError


@dataclass(frozen=True, slots=True)
class StaffPrincipal:
    id: str
    role: Literal["methodist", "admin"]
    root_guest_id: str
    session_id: str

    @property
    def account_id(self) -> str:
        return self.id


def authorize_staff(
    db: Session, token: str | None, now: datetime, *, publish: bool = False, write: bool = False,
    clock: Callable[[], datetime] | None = None,
) -> StaffPrincipal:
    account, access, root = account_session(db, token, now, write=write, clock=clock)
    statement = select(TotpCredential).where(TotpCredential.account_id == account.id)
    if write:
        statement = statement.with_for_update()
    mfa = db.scalar(statement.execution_options(populate_existing=True))
    now = clock() if clock is not None else now
    _check_session(account, access, root, token, now)
    if account.role not in {"methodist", "admin"}:
        raise ApiError(403, "staff_required", "Нужна роль методиста или администратора.")
    if publish and account.role != "admin":
        raise ApiError(403, "admin_required", "Публикация доступна только администратору.")
    if mfa is None or mfa.confirmed_at is None or mfa_until(access, now) is None:
        raise ApiError(403, "mfa_required", "Подтвердите MFA для административного доступа.")
    return StaffPrincipal(account.id, account.role, root.id, access.id)


def require_staff(request: Request, publish: bool = False) -> StaffPrincipal:
    accounts = request.app.state.accounts
    if not accounts.available:
        raise ApiError(503, "accounts_disabled", "Вход по email сейчас недоступен.")
    if not accounts.config.mfa_encryption_key:
        raise ApiError(503, "mfa_unavailable", "MFA сейчас недоступна.")
    token = request.cookies.get(request.app.state.settings.cookie_name)
    with accounts.database.transaction() as db:
        return authorize_staff(
            db, token, accounts.clock(), publish=publish, clock=accounts.clock,
        )
