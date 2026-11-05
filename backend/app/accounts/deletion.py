"""Root-serialized cancellation and atomic, exact-request account erasure.

The active queue only contains requests that may still execute. Cancellation
moves an ID to private terminal storage. Completion removes the account and
its origins, and commits a detached receipt in the same transaction.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.accounts.authorization import StaffPrincipal, authorize_staff
from app.accounts.locks import lock_auth_bucket
from app.accounts.models import (
    AccessSession,
    Account,
    AccountConsent,
    AccountDeletionCancellation,
    AccountDeletionReceipt,
    AccountDeletionRequest,
    AccountRoleAudit,
    GuestClaim,
    MagicLink,
    TotpCredential,
)
from app.accounts.principals import _check_session, account_session
from app.accounts.schemas import DeletionCancellation, DeletionReceipt
from app.assessments.models import AssessmentRecord
from app.database import Database
from app.errors import ApiError, not_found
from app.learning.models import EvidenceRecord, LearningState, TaskAnnotation
from app.models import AttemptRecord, Guest, IdempotencyRecord, LearningSessionRecord, SeenTask


def _receipt_view(record: AccountDeletionReceipt) -> DeletionReceipt:
    return DeletionReceipt(
        request_id=record.request_id, scope=record.scope,
        requested_at=record.requested_at.isoformat(), deadline_at=record.deadline_at.isoformat(),
        completed_at=record.completed_at.isoformat(),
    )


def _cancellation_view(record: AccountDeletionCancellation) -> DeletionCancellation:
    return DeletionCancellation(
        id=record.id, requested_at=record.requested_at.isoformat(),
        deadline_at=record.deadline_at.isoformat(), canceled_at=record.canceled_at.isoformat(),
    )


def _origins(db: Session, account: Account) -> list[str]:
    return sorted({account.root_guest_id, *db.scalars(
        select(GuestClaim.guest_id).where(GuestClaim.account_id == account.id),
    )})


def _terminal(db: Session, request_id: str) -> DeletionReceipt:
    receipt = db.get(AccountDeletionReceipt, request_id)
    if receipt is not None:
        return _receipt_view(receipt)
    if db.get(AccountDeletionCancellation, request_id) is not None:
        raise ApiError(409, "deletion_canceled", "Этот запрос удаления отменён.")
    raise not_found()


def _operator_alias(value: str, aliases: dict[str, str]) -> str:
    """Keep opaque operator UUIDs; replace free text without retaining a reverse map."""
    try:
        if str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    key = value.casefold()
    if key not in aliases:
        aliases[key] = f"deleted-operator:{uuid4()}"
    return aliases[key]


class DeletionService:
    def __init__(self, database: Database, clock: Callable[[], datetime]) -> None:
        self.database, self.clock = database, clock

    def _admin(self, db: Session, credential: str | None, *, write: bool) -> StaffPrincipal:
        actor = authorize_staff(
            db, credential, self.clock(), write=write, clock=self.clock,
        )
        if actor.role != "admin":
            raise ApiError(403, "admin_required", "Исполнение удаления доступно администратору.")
        return actor

    def cancel(self, credential: str | None, request_id: str) -> DeletionCancellation:
        with self.database.transaction(write=True) as db:
            account, access, root = account_session(
                db, credential, self.clock(), write=True, clock=self.clock,
            )
            request = db.scalar(select(AccountDeletionRequest).where(
                AccountDeletionRequest.id == request_id,
                AccountDeletionRequest.account_id == account.id,
            ).with_for_update().execution_options(populate_existing=True))
            canceled = db.scalar(select(AccountDeletionCancellation).where(
                AccountDeletionCancellation.id == request_id,
                AccountDeletionCancellation.account_id == account.id,
            ).with_for_update().execution_options(populate_existing=True))
            now = self.clock()
            _check_session(account, access, root, credential, now)
            if canceled is not None:
                return _cancellation_view(canceled)
            if request is None:
                raise not_found()
            if now < request.requested_at:
                raise ApiError(409, "deletion_clock_invalid", "Время запроса ещё не наступило.")
            canceled = AccountDeletionCancellation(
                id=request.id, account_id=account.id, requested_at=request.requested_at,
                deadline_at=request.deadline_at, canceled_at=now,
            )
            db.add(canceled)
            db.delete(request)
            db.flush()
            return _cancellation_view(canceled)

    def receipt(self, credential: str | None, request_id: str) -> DeletionReceipt:
        with self.database.transaction() as db:
            self._admin(db, credential, write=False)
            record = db.get(AccountDeletionReceipt, request_id)
            if record is None:
                raise not_found()
            return _receipt_view(record)

    def fulfill(
        self, credential: str | None, request_id: str, *, confirm: bool,
    ) -> DeletionReceipt:
        if not confirm:
            raise ApiError(422, "confirmation_required", "Подтвердите исполнение удаления.")
        with self.database.transaction(write=True) as db:
            actor = self._admin(db, credential, write=False)
            # Login completion locks link -> roots; issuance can insert email-only
            # links. Take both existing barriers BEFORE roots to avoid inversion
            # and prevent either path from resurrecting credentials during erasure.
            for key in ("complete-link", "request-link"):
                lock_auth_bucket(db, key)
            request = db.get(AccountDeletionRequest, request_id)
            if request is None:
                self._admin(db, credential, write=True)
                return _terminal(db, request_id)
            account = db.get(Account, request.account_id)
            origins = _origins(db, account)
            roots = list(db.scalars(select(Guest).where(
                Guest.id.in_(sorted({*origins, actor.root_guest_id})),
            ).order_by(Guest.id).with_for_update().execution_options(populate_existing=True)))
            # Acquire ALL owner roots first, then accounts in a deterministic order.
            accounts = {item.id: item for item in db.scalars(select(Account).where(
                Account.id.in_(sorted({account.id, actor.id})),
            ).order_by(Account.id).with_for_update().execution_options(populate_existing=True))}
            target = accounts.get(account.id)
            current_actor = self._admin(db, credential, write=True)
            if current_actor != actor:
                raise ApiError(403, "deletion_actor_changed", "Сеанс изменился. Войдите заново.")
            request = db.scalar(select(AccountDeletionRequest).where(
                AccountDeletionRequest.id == request_id,
            ).with_for_update().execution_options(populate_existing=True))
            if request is None:
                self._admin(db, credential, write=True)
                return _terminal(db, request_id)
            if (
                target is None or request.account_id != target.id or origins != _origins(db, target)
                or not set(origins) <= {root.id for root in roots}
                or db.scalar(select(Account.id).where(
                    Account.root_guest_id.in_(origins), Account.id != target.id,
                )) is not None
                or db.scalar(select(GuestClaim.guest_id).where(
                    GuestClaim.guest_id.in_(origins), GuestClaim.account_id != target.id,
                )) is not None
            ):
                raise ApiError(409, "deletion_scope_changed", "Область владельца изменилась.")

            sessions = list(db.scalars(select(AccessSession).where(
                AccessSession.account_id == target.id,
            ).order_by(AccessSession.id).with_for_update().execution_options(populate_existing=True)))
            db.scalar(select(TotpCredential).where(
                TotpCredential.account_id == target.id,
            ).with_for_update().execution_options(populate_existing=True))
            digests = {root.token_digest for root in roots if root.id in origins}
            digests.update(access.token_digest for access in sessions)
            # Original guest secrets and pre-rotation account bearers can occur in
            # older link bindings, even when the current credential has changed.
            digests.update(db.scalars(select(MagicLink.browser_credential_digest).where(
                or_(MagicLink.guest_id.in_(origins), MagicLink.credential_account_id == target.id),
                MagicLink.browser_credential_digest.is_not(None),
            )))
            link_ids = list(db.scalars(select(MagicLink.id).where(or_(
                MagicLink.email == target.email, MagicLink.guest_id.in_(origins),
                MagicLink.credential_account_id == target.id,
                MagicLink.browser_credential_digest.in_(sorted(digests)),
            )).order_by(MagicLink.id).with_for_update()))
            audits = list(db.scalars(select(AccountRoleAudit).where(or_(
                AccountRoleAudit.account_id == target.id,
                func.lower(AccountRoleAudit.operator).contains(target.email, autoescape=True),
            )).order_by(AccountRoleAudit.id).with_for_update()
                .execution_options(populate_existing=True)))
            # Authorization time is sampled again after every potentially blocking
            # credential/request/audit lock, not inherited from preflight.
            self._admin(db, credential, write=True)
            now = self.clock()
            if (
                request.status != "requested" or request.requested_at > now
                or request.deadline_at != request.requested_at + timedelta(days=30)
            ):
                raise ApiError(409, "deletion_request_invalid", "Некорректный запрос удаления.")
            receipt = AccountDeletionReceipt(
                request_id=request.id, requested_at=request.requested_at,
                deadline_at=request.deadline_at, completed_at=now, scope="active_cloud_v1",
            )
            self._purge(db, target, origins, link_ids, audits)
            receipt.completed_at = self.clock()
            db.add(receipt)
            db.flush()
            return _receipt_view(receipt)

    @staticmethod
    def _purge(
        db: Session, account: Account, origins: list[str], link_ids: list[str],
        audits: list[AccountRoleAudit],
    ) -> None:
        aliases: dict[str, str] = {}
        for audit in audits:
            if audit.account_id == account.id:
                audit.subject_id, audit.account_id = account.id, None
            audit.operator = _operator_alias(audit.operator, aliases)
        db.flush()
        # No cascades or broad deletes: every removal has an exact account/origin
        # predicate. Remove dependents before their parents, with FK checks enabled.
        db.execute(delete(MagicLink).where(MagicLink.id.in_(link_ids)))
        db.execute(delete(TotpCredential).where(TotpCredential.account_id == account.id))
        db.execute(delete(AccessSession).where(AccessSession.account_id == account.id))
        for model in (TaskAnnotation, EvidenceRecord, LearningState):
            db.execute(delete(model).where(model.owner_id.in_(origins)))
        for model in (
            IdempotencyRecord, AssessmentRecord, AttemptRecord, SeenTask, LearningSessionRecord,
        ):
            db.execute(delete(model).where(model.guest_id.in_(origins)))
        for model in (
            AccountConsent, AccountDeletionCancellation, AccountDeletionRequest, GuestClaim,
        ):
            db.execute(delete(model).where(model.account_id == account.id))
        db.execute(delete(Account).where(Account.id == account.id))
        db.execute(delete(Guest).where(Guest.id.in_(origins)))
