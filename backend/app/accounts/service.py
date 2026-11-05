"""Email login and account changes inside explicit database transactions."""

import logging
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.config import LINK_TTL_SECONDS, SESSION_DAYS, AccountSettings
from app.accounts.deletion import DeletionService
from app.accounts.locks import lock_auth_bucket
from app.accounts.mail import MailSender, SMTPMailSender
from app.accounts.mfa import MFAService, mfa_until
from app.accounts.models import (
    AccessSession,
    Account,
    AccountConsent,
    AccountDeletionRequest,
    GuestClaim,
    MagicLink,
    TotpCredential,
)
from app.accounts.principals import _check_session, account_session, owner_ids
from app.accounts.schemas import (
    AccessSessionView,
    AccountExport,
    AccountPatch,
    AccountView,
    ActiveSessions,
    AuthConfig,
    ConsentView,
    DeletionCancellation,
    DeletionReceipt,
    DeletionStatus,
    DeletionView,
    LinkRequest,
    MFAEnrollment,
    MFAStatus,
)
from app.accounts.tokens import new_token, token_digest
from app.errors import ApiError, not_found
from app.models import AttemptRecord, Guest, LearningSessionRecord
from app.presentation import session_view

if TYPE_CHECKING:
    from app.services import LearningService

logger = logging.getLogger(__name__)


def _invalid_link() -> ApiError:
    return ApiError(400, "invalid_link", "Ссылка недействительна. Запросите новую в этом браузере.")


def _deletion_view(record: AccountDeletionRequest | None) -> DeletionView | None:
    if record is None:
        return None
    return DeletionView(
        id=record.id, status=record.status, requested_at=record.requested_at.isoformat(),
        deadline_at=record.deadline_at.isoformat(),
    )


def _consume_limit(db: Session, key: str, clock: Callable[[], datetime], limit: int) -> bool:
    """A bounded rolling-hour log under a cross-worker database row lock."""
    bucket = lock_auth_bucket(db, key)
    instant = clock().timestamp()
    events = [event for event in bucket.events if event > instant - 3600]
    if len(events) >= limit:
        return False
    bucket.events = [*events, instant]
    return True


class AccountService:
    def __init__(
        self, learning_service: "LearningService", config: AccountSettings | None = None,
        mail_sender: MailSender | None = None,
    ) -> None:
        self.learning = learning_service
        self.database = learning_service.database
        self.clock = learning_service.clock
        self.config = config if config is not None else AccountSettings.from_env()
        if mail_sender is not None and learning_service.settings.environment != "test":
            raise ValueError("Injectable email delivery is restricted to the test environment")
        if self.config.public_origin is not None:
            if self.config.public_origin not in learning_service.settings.allowed_origins:
                raise ValueError("ACCOUNTS_PUBLIC_ORIGIN must be an allowed application origin")
            if (
                learning_service.settings.environment != "test"
                and self.config.policy_ready
                and not self.config.public_origin.startswith("https://")
            ):
                raise ValueError("Email account login requires HTTPS outside isolated tests")
        self.mail_sender = mail_sender or (
            SMTPMailSender(self.config) if self.config.smtp_ready else None
        )
        self.mfa = MFAService(learning_service, self.config)
        self.deletion = DeletionService(self.database, self.clock)

    @property
    def available(self) -> bool:
        return self.config.policy_ready and (self.config.smtp_ready or self.mail_sender is not None)

    def configuration(self) -> AuthConfig:
        return AuthConfig(
            enabled=self.available,
            policy_version=self.config.policy_version if self.available else None,
            policy_url=self.config.policy_url if self.available else None,
            link_ttl_seconds=LINK_TTL_SECONDS,
        )

    def _enabled(self) -> None:
        if not self.available:
            raise ApiError(503, "accounts_disabled", "Вход по email сейчас недоступен.")

    def request_link(
        self, request: LinkRequest, credential: str | None, browser_state: str | None,
    ) -> str:
        self._enabled()
        if not request.accept_policy or request.policy_version != self.config.policy_version:
            raise ApiError(
                422, "consent_required", "Подтвердите действующую политику обработки данных.",
            )
        state = browser_state if token_digest(browser_state) is not None else new_token()
        link_token = None
        with self.database.transaction(write=True) as db:
            allowed = _consume_limit(db, "request-link", self.clock, 100)
            now = self.clock()
            expires_at = now + timedelta(seconds=LINK_TTL_SECONDS)
            recent = db.scalar(select(func.count()).select_from(MagicLink).where(
                MagicLink.email == request.email, MagicLink.created_at > now - timedelta(hours=1),
            ))
            if allowed and recent < 5:
                digest = token_digest(credential)
                guest = (
                    db.scalar(select(Guest).where(Guest.token_digest == digest)) if digest else None
                )
                claimable = (
                    guest is not None and guest.expires_at > now
                    and db.get(GuestClaim, guest.id) is None
                )
                credential_account_id = db.scalar(select(AccessSession.account_id).where(
                    AccessSession.token_digest == digest,
                )) if digest else None
                if credential_account_id is None and guest is not None:
                    credential_account_id = db.scalar(select(GuestClaim.account_id).where(
                        GuestClaim.guest_id == guest.id,
                    ))
                link_token = new_token()
                db.add(MagicLink(
                    id=str(uuid4()), email=request.email, token_digest=token_digest(link_token),
                    browser_state_digest=token_digest(state), browser_credential_digest=digest,
                    credential_account_id=credential_account_id,
                    guest_id=guest.id if claimable else None, policy_version=request.policy_version,
                    created_at=now, expires_at=expires_at, consumed_at=None,
                ))
        if link_token is not None:
            try:
                self.mail_sender.send_login_link(
                    request.email, f"{self.config.public_origin}/account#token={link_token}",
                    expires_at,
                )
            except Exception as exc:
                # SMTP exceptions may embed the recipient or server credentials.
                logger.warning("Account mail delivery failed (%s)", type(exc).__name__)
        return state

    def complete(
        self, link_token: str, browser_state: str | None, credential: str | None,
    ) -> tuple[AccountView, str]:
        self._enabled()
        error = None
        result = None
        with self.database.transaction(write=True) as db:
            if not _consume_limit(db, "complete-link", self.clock, 500):
                error = ApiError(
                    429, "auth_rate_limited", "Слишком много запросов. Попробуйте позже.",
                )
            else:
                try:
                    with db.begin_nested():
                        result = self._complete(db, link_token, browser_state, credential)
                except ApiError as exc:
                    error = exc
        if error is not None:
            raise error
        return result

    def _complete(
        self, db: Session, link_token: str, browser_state: str | None,
        credential: str | None,
    ) -> tuple[AccountView, str]:
        digest, state_digest = token_digest(link_token), token_digest(browser_state)
        link = db.scalar(
            select(MagicLink).where(MagicLink.token_digest == digest).with_for_update()
            .execution_options(populate_existing=True),
        )
        if (
            link is None or state_digest is None or link.consumed_at is not None
            or link.token_digest != digest or link.policy_version != self.config.policy_version
            or not secrets.compare_digest(link.browser_state_digest, state_digest)
            or link.browser_credential_digest != token_digest(credential)
        ):
            raise _invalid_link()

        account = db.scalar(select(Account).where(Account.email == link.email))
        roots = {account.root_guest_id} if account is not None else set()
        if link.guest_id is not None:
            roots.add(link.guest_id)
        locked = {guest.id: guest for guest in db.scalars(
            select(Guest).where(Guest.id.in_(sorted(roots))).order_by(Guest.id)
            .with_for_update().execution_options(populate_existing=True)
        )}
        source = locked.get(link.guest_id)
        claim = db.get(GuestClaim, source.id) if source is not None else None
        old, active = None, []
        if account is not None:
            db.refresh(account, with_for_update=True)
            old = db.scalar(select(AccessSession).where(
                AccessSession.account_id == account.id,
                AccessSession.token_digest == token_digest(credential),
            ).with_for_update().execution_options(populate_existing=True))
            active = list(db.scalars(select(AccessSession).where(
                AccessSession.account_id == account.id, AccessSession.revoked_at.is_(None),
            ).order_by(AccessSession.created_at.desc(), AccessSession.id.desc())
                .with_for_update().execution_options(populate_existing=True)))

        # The link's binding/consumption is stable under its lock, but its deadline
        # keeps advancing while root, account, or access-session locks are awaited.
        now = self.clock()
        if link.expires_at <= now:
            raise _invalid_link()
        if link.guest_id is not None and (
            source is None or source.token_digest != link.browser_credential_digest
            or source.expires_at <= now or claim is not None
        ):
            raise _invalid_link()
        if account is None:
            root = Guest(
                id=str(uuid4()), token_digest=token_digest(new_token()), created_at=now,
                expires_at=now, last_seen_at=now,
            )
            db.add(root)
            db.flush()
            account = Account(
                id=str(uuid4()), email=link.email, root_guest_id=root.id, role="student",
                created_at=now, email_verified_at=now, policy_version=link.policy_version,
                consented_at=now, daily_minutes=20,
            )
            db.add(account)
            db.flush()
            db.add(GuestClaim(guest_id=root.id, account_id=account.id, claimed_at=now))
        if source is not None:
            db.add(GuestClaim(guest_id=source.id, account_id=account.id, claimed_at=now))
            source.token_digest = token_digest(new_token())
            source.expires_at = now
        if db.scalar(select(AccountConsent.id).where(
            AccountConsent.account_id == account.id,
            AccountConsent.policy_version == link.policy_version,
        )) is None:
            db.add(AccountConsent(
                id=str(uuid4()), account_id=account.id, policy_version=link.policy_version,
                accepted_at=now,
            ))
            account.policy_version, account.consented_at = link.policy_version, now
        link.consumed_at = now
        if old is not None:
            old.revoked_at = now
        active = [
            access for access in active if access.revoked_at is None and access.expires_at > now
        ]
        for stale in active[9:]:
            stale.revoked_at = now
        access_token = new_token()
        access = AccessSession(
            id=str(uuid4()), account_id=account.id, token_digest=token_digest(access_token),
            created_at=now, expires_at=now + timedelta(days=SESSION_DAYS), last_seen_at=now,
            revoked_at=None, mfa_verified_at=None,
        )
        db.add(access)
        db.flush()
        return self._view(db, account, access), access_token

    def _view(self, db: Session, account: Account, access: AccessSession) -> AccountView:
        mfa = db.get(TotpCredential, account.id)
        return AccountView(
            id=account.id, email=account.email,
            email_verified=account.email_verified_at is not None,
            role=account.role, root_guest_id=account.root_guest_id,
            owner_ids=owner_ids(db, db.get(Guest, account.root_guest_id)),
            created_at=account.created_at.isoformat(), policy_version=account.policy_version,
            consented_at=account.consented_at.isoformat(), daily_minutes=account.daily_minutes,
            mfa_enabled=mfa is not None and mfa.confirmed_at is not None,
            mfa_verified_until=mfa_until(access, self.clock()),
        )

    def get_account(self, credential: str | None) -> AccountView:
        with self.database.transaction() as db:
            account, access, _ = account_session(db, credential, self.clock(), clock=self.clock)
            return self._view(db, account, access)

    def export(self, credential: str | None) -> AccountExport:
        with self.database.transaction() as db:
            account, access, root = account_session(db, credential, self.clock(), clock=self.clock)
            origins = owner_ids(db, root)
            sessions = list(db.scalars(
                select(LearningSessionRecord).where(LearningSessionRecord.guest_id.in_(origins))
                .order_by(LearningSessionRecord.created_at, LearningSessionRecord.id)
            ))
            by_session = {session.id: [] for session in sessions}
            for attempt in db.scalars(
                select(AttemptRecord).where(AttemptRecord.guest_id.in_(origins))
                .order_by(AttemptRecord.session_id, AttemptRecord.sequence)
            ):
                if attempt.session_id in by_session:
                    by_session[attempt.session_id].append(attempt)
            return AccountExport(
                version="1", exported_at=self.clock().isoformat(),
                account=self._view(db, account, access),
                sessions=[session_view(session, by_session[session.id]) for session in sessions],
                consents=[ConsentView(
                    policy_version=consent.policy_version,
                    accepted_at=consent.accepted_at.isoformat(),
                ) for consent in db.scalars(
                    select(AccountConsent).where(AccountConsent.account_id == account.id)
                    .order_by(AccountConsent.accepted_at, AccountConsent.policy_version)
                )],
                deletion_request=_deletion_view(db.scalar(select(AccountDeletionRequest).where(
                    AccountDeletionRequest.account_id == account.id,
                ))),
            )

    def update_account(self, credential: str | None, request: AccountPatch) -> AccountView:
        with self.database.transaction(write=True) as db:
            account, access, _ = account_session(
                db, credential, self.clock(), write=True, clock=self.clock,
            )
            account.daily_minutes = request.daily_minutes
            return self._view(db, account, access)

    def active_sessions(self, credential: str | None) -> ActiveSessions:
        with self.database.transaction() as db:
            account, current, _ = account_session(db, credential, self.clock(), clock=self.clock)
            now = self.clock()
            return ActiveSessions(sessions=[AccessSessionView(
                id=access.id, created_at=access.created_at.isoformat(),
                last_seen_at=access.last_seen_at.isoformat(),
                expires_at=access.expires_at.isoformat(),
                current=access.id == current.id, mfa_verified_until=mfa_until(access, now),
            ) for access in db.scalars(select(AccessSession).where(
                AccessSession.account_id == account.id, AccessSession.revoked_at.is_(None),
                AccessSession.expires_at > now,
            ).order_by(AccessSession.created_at.desc(), AccessSession.id.desc()))])

    def revoke_session(self, credential: str | None, session_id: str) -> bool:
        with self.database.transaction(write=True) as db:
            account, current, root = account_session(
                db, credential, self.clock(), write=True, clock=self.clock,
            )
            target = db.scalar(select(AccessSession).where(
                AccessSession.id == session_id, AccessSession.account_id == account.id,
            ).with_for_update().execution_options(populate_existing=True))
            now = self.clock()
            _check_session(account, current, root, credential, now)
            if target is None:
                raise not_found()
            target.revoked_at = now
            return target.id == current.id

    def logout(self, credential: str | None) -> None:
        with self.database.transaction(write=True) as db:
            try:
                account, access, root = account_session(
                    db, credential, self.clock(), write=True, clock=self.clock,
                )
                now = self.clock()
                _check_session(account, access, root, credential, now)
            except ApiError as exc:
                if exc.status_code == 401:
                    return
                raise
            access.revoked_at = now

    def deletion_status(self, credential: str | None) -> DeletionStatus:
        with self.database.transaction() as db:
            account, _, _ = account_session(db, credential, self.clock(), clock=self.clock)
            record = db.scalar(select(AccountDeletionRequest).where(
                AccountDeletionRequest.account_id == account.id,
            ))
            return DeletionStatus(request=_deletion_view(record))

    def request_deletion(self, credential: str | None, *, confirm: bool) -> DeletionStatus:
        if not confirm:
            raise ApiError(422, "confirmation_required", "Подтвердите запрос удаления аккаунта.")
        with self.database.transaction(write=True) as db:
            account, access, root = account_session(
                db, credential, self.clock(), write=True, clock=self.clock,
            )
            record = db.scalar(select(AccountDeletionRequest).where(
                AccountDeletionRequest.account_id == account.id,
            ))
            now = self.clock()
            _check_session(account, access, root, credential, now)
            if record is None:
                record = AccountDeletionRequest(
                    id=str(uuid4()), account_id=account.id, requested_at=now,
                    deadline_at=now + timedelta(days=30), status="requested",
                )
                db.add(record)
            return DeletionStatus(request=_deletion_view(record))

    def enroll_mfa(self, credential: str | None) -> MFAEnrollment:
        self._enabled()
        return self.mfa.enroll(credential)

    def cancel_deletion(self, credential: str | None, request_id: str) -> DeletionCancellation:
        return self.deletion.cancel(credential, request_id)

    def fulfill_deletion(
        self, credential: str | None, request_id: str, *, confirm: bool,
    ) -> DeletionReceipt:
        return self.deletion.fulfill(credential, request_id, confirm=confirm)

    def deletion_receipt(self, credential: str | None, request_id: str) -> DeletionReceipt:
        return self.deletion.receipt(credential, request_id)

    def verify_mfa(
        self, credential: str | None, code: str, *, enrollment: bool = False,
    ) -> tuple[MFAStatus, str, int]:
        self._enabled()
        return self.mfa.verify(credential, code, enrollment=enrollment)
