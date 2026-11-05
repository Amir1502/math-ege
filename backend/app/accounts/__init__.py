"""Optional email accounts, durable ownership and staff authentication."""

from app.accounts.authorization import StaffPrincipal, authorize_staff, require_staff

__all__ = ["StaffPrincipal", "authorize_staff", "require_staff"]
