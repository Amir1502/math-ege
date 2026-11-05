"""Optional account HTTP routes mounted by the application factory."""

from fastapi import APIRouter, Request, Response

from app.accounts.authorization import require_staff as require_staff
from app.accounts.config import LINK_TTL_SECONDS, SESSION_DAYS
from app.accounts.schemas import (
    AccountExport,
    AccountPatch,
    AccountView,
    ActiveSessions,
    AuthConfig,
    DeletionCancellation,
    DeletionReceipt,
    DeletionRequest,
    DeletionStatus,
    LinkComplete,
    LinkRequest,
    Message,
    MFACode,
    MFAEnrollment,
    MFAStatus,
    Success,
)
from app.accounts.service import AccountService
from app.schemas import EmptyRequest

router = APIRouter(prefix="/api/v1", tags=["accounts"])
STATE_COOKIE = "math_ege_auth_state"


def service(request: Request) -> AccountService:
    return request.app.state.accounts


def token(request: Request) -> str | None:
    return request.cookies.get(request.app.state.settings.cookie_name)


def _cookie(request: Request, response: Response, name: str, value: str, seconds: int) -> None:
    response.set_cookie(
        name, value, max_age=seconds, path="/", httponly=True,
        secure=request.app.state.settings.cookie_secure, samesite="strict",
    )


@router.get("/auth/config", response_model=AuthConfig)
def configuration(request: Request) -> AuthConfig:
    return service(request).configuration()


@router.post("/auth/request-link", status_code=202, response_model=Message)
def request_link(request: Request, body: LinkRequest, response: Response) -> Message:
    state = service(request).request_link(body, token(request), request.cookies.get(STATE_COOKIE))
    _cookie(request, response, STATE_COOKIE, state, LINK_TTL_SECONDS)
    return Message(message="Если адрес доступен для входа, письмо со ссылкой отправлено.")


@router.post("/auth/complete", response_model=AccountView)
def complete(request: Request, body: LinkComplete, response: Response) -> AccountView:
    account, credential = service(request).complete(
        body.token, request.cookies.get(STATE_COOKIE), token(request),
    )
    _cookie(
        request, response, request.app.state.settings.cookie_name, credential, SESSION_DAYS * 86400,
    )
    _cookie(request, response, STATE_COOKIE, "", 0)
    return account


@router.get("/account", response_model=AccountView)
def account(request: Request) -> AccountView:
    return service(request).get_account(token(request))


@router.get("/account/export", response_model=AccountExport)
def export(request: Request) -> AccountExport:
    return service(request).export(token(request))


@router.patch("/account", response_model=AccountView)
def update_account(request: Request, body: AccountPatch) -> AccountView:
    return service(request).update_account(token(request), body)


@router.get("/account/sessions", response_model=ActiveSessions)
def active_sessions(request: Request) -> ActiveSessions:
    return service(request).active_sessions(token(request))


@router.post("/account/sessions/{session_id}/revoke", response_model=Success)
def revoke_session(
    request: Request, session_id: str, body: EmptyRequest, response: Response,
) -> Success:
    if service(request).revoke_session(token(request), session_id):
        _cookie(request, response, request.app.state.settings.cookie_name, "", 0)
        _cookie(request, response, STATE_COOKIE, "", 0)
    return Success()


@router.post("/auth/logout", response_model=Success)
def logout(request: Request, body: EmptyRequest, response: Response) -> Success:
    service(request).logout(token(request))
    _cookie(request, response, request.app.state.settings.cookie_name, "", 0)
    _cookie(request, response, STATE_COOKIE, "", 0)
    return Success()


@router.get("/account/deletion-request", response_model=DeletionStatus)
def deletion_status(request: Request) -> DeletionStatus:
    return service(request).deletion_status(token(request))


@router.post("/account/deletion-request", response_model=DeletionStatus)
def request_deletion(request: Request, body: DeletionRequest) -> DeletionStatus:
    return service(request).request_deletion(token(request), confirm=body.confirm)


@router.post("/account/deletion-request/{request_id}/cancel", response_model=DeletionCancellation)
def cancel_deletion(
    request: Request, request_id: str, body: EmptyRequest,
) -> DeletionCancellation:
    return service(request).cancel_deletion(token(request), request_id)


@router.post("/admin/account-deletions/{request_id}/fulfill", response_model=DeletionReceipt)
def fulfill_deletion(
    request: Request, request_id: str, body: DeletionRequest,
) -> DeletionReceipt:
    return service(request).fulfill_deletion(token(request), request_id, confirm=body.confirm)


@router.get("/admin/account-deletions/{request_id}/receipt", response_model=DeletionReceipt)
def deletion_receipt(request: Request, request_id: str) -> DeletionReceipt:
    return service(request).deletion_receipt(token(request), request_id)


@router.post("/auth/mfa/enroll", response_model=MFAEnrollment)
def enroll_mfa(request: Request, body: EmptyRequest) -> MFAEnrollment:
    return service(request).enroll_mfa(token(request))


def _verify_mfa(
    request: Request, body: MFACode, response: Response, *, enrollment: bool,
) -> MFAStatus:
    status, credential, seconds = service(request).verify_mfa(
        token(request), body.code, enrollment=enrollment,
    )
    _cookie(request, response, request.app.state.settings.cookie_name, credential, seconds)
    return status


@router.post("/auth/mfa/confirm", response_model=MFAStatus)
def confirm_mfa(request: Request, body: MFACode, response: Response) -> MFAStatus:
    return _verify_mfa(request, body, response, enrollment=True)


@router.post("/auth/mfa/verify", response_model=MFAStatus)
def verify_mfa(request: Request, body: MFACode, response: Response) -> MFAStatus:
    return _verify_mfa(request, body, response, enrollment=False)
