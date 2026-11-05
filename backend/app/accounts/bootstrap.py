"""Local-operator role assignment for an existing verified, MFA-enrolled account.

Never invoked by app startup or an HTTP route. No accounts or secrets are seeded.
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.models import AccessSession, Account, AccountRoleAudit, TotpCredential
from app.accounts.schemas import normalize_email
from app.config import Settings
from app.database import Database
from app.models import Guest


def assign_role(
    database: Database, *, email: str, role: str, operator: str, now: datetime,
) -> str:
    """Trusted local command seam; callers require direct database authority."""
    email = normalize_email(email)
    if role not in {"student", "methodist", "admin"}:
        raise ValueError("Choose an explicit supported role")
    if not 1 <= len(operator.strip()) <= 128 or any(ord(char) < 32 for char in operator):
        raise ValueError("An explicit local operator identifier is required")
    with database.transaction(write=True) as db:
        account = db.scalar(select(Account).where(Account.email == email))
        if account is None or account.email_verified_at is None:
            raise ValueError("The account must first complete verified email login")
        db.scalar(select(Guest).where(Guest.id == account.root_guest_id).with_for_update())
        db.refresh(account)
        mfa = db.get(TotpCredential, account.id)
        if role != "student" and (mfa is None or mfa.confirmed_at is None):
            raise ValueError("Confirmed MFA enrollment is required before assigning a staff role")
        if account.role != role:
            db.add(AccountRoleAudit(
                id=str(uuid4()), account_id=account.id, previous_role=account.role,
                new_role=role, operator=operator.strip(), changed_at=now,
            ))
            account.role = role
            for access in db.scalars(select(AccessSession).where(
                AccessSession.account_id == account.id, AccessSession.revoked_at.is_(None),
            )):
                access.revoked_at = now
        return account.id


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--email", required=True, help="Existing verified account email")
    result.add_argument("--role", required=True, choices=("student", "methodist", "admin"))
    result.add_argument("--operator", required=True, help="Local operator identity for the audit")
    result.add_argument("--confirm-role-change", required=True, action="store_true")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    database = Database(Settings.from_env())
    try:
        account_id = assign_role(
            database, email=arguments.email, role=arguments.role,
            operator=arguments.operator, now=datetime.now(UTC),
        )
    except (ValueError, SQLAlchemyError) as exc:
        # Database exception text can include bound email addresses or connection secrets.
        print(f"Role assignment failed ({type(exc).__name__}).", file=sys.stderr)
        return 1
    finally:
        database.dispose()
    print(f"Role assignment recorded for account {account_id}; existing sessions revoked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
