"""Vetted TOTP, encrypted at rest, with root-serialized replay/attempt checks."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.accounts.config import MFA_RECENCY_SECONDS, AccountSettings
from app.accounts.models import AccessSession, TotpCredential
from app.accounts.principals import _check_session, account_session
from app.accounts.schemas import MFAEnrollment, MFAStatus
from app.accounts.tokens import new_token, token_digest
from app.errors import ApiError

if TYPE_CHECKING:
    from app.services import LearningService


def mfa_until(access: AccessSession, now: datetime) -> str | None:
    if access.mfa_verified_at is not None:
        deadline = access.mfa_verified_at + timedelta(seconds=MFA_RECENCY_SECONDS)
        if access.mfa_verified_at <= now < deadline:
            return deadline.isoformat()
    return None


def _invalid_code() -> ApiError:
    return ApiError(400, "invalid_mfa", "Код недействителен или уже использован.")


def _matching_timecode(secret: str, code: str, now: datetime) -> int | None:
    authenticator = pyotp.TOTP(secret)
    # Verify each tick through PyOTP so the persisted replay counter is the
    # accepted tick, including a one-step device clock drift in either direction.
    for offset in (-1, 0, 1):
        instant = now + timedelta(seconds=offset * authenticator.interval)
        if authenticator.verify(code, for_time=instant):
            return authenticator.timecode(instant)
    return None


class MFAService:
    def __init__(self, learning_service: "LearningService", config: AccountSettings) -> None:
        self.database, self.clock, self.config = (
            learning_service.database, learning_service.clock, config,
        )

    def _cipher(self) -> Fernet:
        if not self.config.mfa_encryption_key:
            raise ApiError(503, "mfa_unavailable", "MFA сейчас недоступна.")
        return Fernet(self.config.mfa_encryption_key)

    def enroll(self, token: str | None) -> MFAEnrollment:
        cipher = self._cipher()
        with self.database.transaction(write=True) as db:
            account, access, root = account_session(
                db, token, self.clock(), write=True, clock=self.clock,
            )
            existing = db.scalar(
                select(TotpCredential).where(TotpCredential.account_id == account.id)
                .with_for_update().execution_options(populate_existing=True)
            )
            now = self.clock()
            _check_session(account, access, root, token, now)
            if not timedelta(0) <= now - access.created_at < timedelta(minutes=15):
                raise ApiError(
                    403, "recent_login_required", "Для настройки MFA повторите вход по email.",
                )
            if existing is not None and (
                existing.confirmed_at is not None or existing.enrollment_expires_at > now
            ):
                raise ApiError(
                    409, "mfa_already_enrolled", "MFA уже настроена или ожидает подтверждения.",
                )
            secret = pyotp.random_base32()
            expires_at = now + timedelta(minutes=10)
            encrypted = cipher.encrypt(secret.encode("ascii")).decode("ascii")
            if existing is None:
                db.add(TotpCredential(
                    account_id=account.id, secret_ciphertext=encrypted,
                    enrollment_session_id=access.id, enrollment_expires_at=expires_at,
                    confirmed_at=None, last_timecode=-1, attempts=[],
                ))
            else:
                existing.secret_ciphertext = encrypted
                existing.enrollment_session_id = access.id
                existing.enrollment_expires_at = expires_at
                existing.last_timecode = -1
            return MFAEnrollment(
                secret=secret,
                provisioning_uri=pyotp.TOTP(secret).provisioning_uri(
                    name=account.email, issuer_name="ЕГЭ Профиль 2027",
                ),
                expires_at=expires_at.isoformat(),
            )

    def verify(
        self, token: str | None, code: str, *, enrollment: bool = False,
    ) -> tuple[MFAStatus, str, int]:
        cipher = self._cipher()
        error, result = None, None
        with self.database.transaction(write=True) as db:
            account, access, root = account_session(
                db, token, self.clock(), write=True, clock=self.clock,
            )
            record = db.scalar(
                select(TotpCredential).where(TotpCredential.account_id == account.id)
                .with_for_update().execution_options(populate_existing=True)
            )
            now = self.clock()
            _check_session(account, access, root, token, now)
            if record is None or (not enrollment and record.confirmed_at is None):
                raise ApiError(409, "mfa_not_enrolled", "Сначала настройте MFA.")
            if enrollment and record.confirmed_at is not None:
                raise ApiError(409, "mfa_already_enrolled", "MFA уже подтверждена.")
            events = [event for event in record.attempts if event > now.timestamp() - 300]
            if len(events) >= 5:
                error = ApiError(
                    429, "mfa_rate_limited", "Слишком много кодов. Подождите пять минут.",
                )
            else:
                record.attempts = [*events, now.timestamp()]
                valid_enrollment = not enrollment or (
                    record.enrollment_session_id == access.id and record.enrollment_expires_at > now
                )
                try:
                    secret = cipher.decrypt(record.secret_ciphertext).decode("ascii")
                except (InvalidToken, UnicodeError) as exc:
                    raise ApiError(503, "mfa_unavailable", "MFA сейчас недоступна.") from exc
                timecode = _matching_timecode(secret, code, now)
                if not valid_enrollment or timecode is None or timecode <= record.last_timecode:
                    error = _invalid_code()
                else:
                    record.last_timecode = timecode
                    if enrollment:
                        record.confirmed_at = now
                    access.mfa_verified_at = now
                    # Privilege elevation invalidates the old bearer, including stolen copies.
                    rotated = new_token()
                    access.token_digest = token_digest(rotated)
                    result = (
                        MFAStatus(enabled=True, verified_until=mfa_until(access, now)),
                        rotated, max(1, int((access.expires_at - now).total_seconds())),
                    )
        # Rejected attempts must commit their throttle state before returning an error.
        if error is not None:
            raise error
        return result
