"""Versioned HTTP routes; domain results never serialize private ORM state."""

from typing import Annotated

from fastapi import APIRouter, Header, Request, Response

from app.errors import ApiError, not_found
from app.schemas import (
    Attempt,
    AttemptRequest,
    CreateSessionRequest,
    DraftRequest,
    DraftRevision,
    EmptyRequest,
    ErrorResponse,
    Export,
    GuestResponse,
    HealthResponse,
    Hint,
    HintRequest,
    LearningSession,
    Lesson,
    Profile,
    Progress,
    Solution,
    SolutionRequest,
)
from app.services import LearningService, StoredResponse

ERROR_RESPONSES = {
    code: {"model": ErrorResponse}
    for code in (400, 401, 403, 404, 409, 413, 415, 422, 500, 503)
}
router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
IdempotencyKey = Annotated[str, Header(min_length=36, max_length=36)]


def service(request: Request) -> LearningService:
    return request.app.state.service


def token(request: Request) -> str | None:
    return request.cookies.get(request.app.state.settings.cookie_name)


def stored_response(result: StoredResponse) -> Response:
    return Response(
        content=result.content, status_code=result.status_code, media_type="application/json"
    )


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    request.app.state.database.check()
    return HealthResponse(status="ok")


@router.get("/profile", response_model=Profile, tags=["content"])
def profile(request: Request) -> Profile:
    return service(request).content().public_profile(
        allow_demo_content=request.app.state.settings.allow_demo_content
    )


@router.get("/lessons/{slot}", response_model=Lesson, tags=["content"])
def lesson(request: Request, slot: int) -> Lesson:
    bundle = service(request).content()
    selected = next((item for item in bundle.lessons if item.slot == slot), None)
    if selected is None:
        raise not_found()
    if not request.app.state.settings.allow_demo_content:
        raise ApiError(503, "demo_content_disabled", "Демонстрационный учебный пакет выключен.")
    return selected


@router.post("/guest", response_model=GuestResponse, tags=["guest"])
def guest(request: Request, body: EmptyRequest, response: Response) -> GuestResponse:
    record, guest_token, lifetime = service(request).guest(token(request))
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.cookie_name, value=guest_token, max_age=lifetime, path="/",
        secure=settings.cookie_secure, httponly=True, samesite="strict",
    )
    return GuestResponse(id=record.id)


@router.post("/sessions", response_model=LearningSession, tags=["practice"])
def create_session(
    request: Request, body: CreateSessionRequest, idempotency_key: IdempotencyKey
) -> Response:
    return stored_response(service(request).create_session(token(request), body, idempotency_key))


@router.get("/sessions/{session_id}", response_model=LearningSession, tags=["practice"])
def get_session(request: Request, session_id: str) -> LearningSession:
    return service(request).get_session(token(request), session_id)


@router.put("/sessions/{session_id}/draft", response_model=DraftRevision, tags=["practice"])
def save_draft(request: Request, session_id: str, body: DraftRequest) -> DraftRevision:
    return service(request).draft(token(request), session_id, body)


@router.post("/sessions/{session_id}/attempts", response_model=Attempt, tags=["practice"])
def submit_attempt(
    request: Request, session_id: str, body: AttemptRequest, idempotency_key: IdempotencyKey
) -> Response:
    return stored_response(
        service(request).attempt(token(request), session_id, body, idempotency_key)
    )


@router.post("/sessions/{session_id}/hints", response_model=Hint, tags=["practice"])
def hint(request: Request, session_id: str, body: HintRequest) -> Hint:
    return service(request).hint(token(request), session_id, body)


@router.post("/sessions/{session_id}/solution", response_model=Solution, tags=["practice"])
def solution(request: Request, session_id: str, body: SolutionRequest) -> Solution:
    return service(request).solution(token(request), session_id, body)


@router.post("/sessions/{session_id}/finish", response_model=LearningSession, tags=["practice"])
def finish(
    request: Request, session_id: str, body: EmptyRequest, idempotency_key: IdempotencyKey
) -> Response:
    return stored_response(
        service(request).finish(token(request), session_id, body, idempotency_key)
    )


@router.get("/progress", response_model=Progress, tags=["history"])
def progress(request: Request) -> Progress:
    return service(request).progress(token(request))


@router.get("/export", response_model=Export, tags=["history"])
def export(request: Request) -> Export:
    return service(request).export(token(request))
