"""Learning HTTP routes share the application's identity and request protection."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api import ERROR_RESPONSES, IdempotencyKey, stored_response, token
from app.learning.schemas import AnnotationRequest, AnnotationView, Dashboard, LearningExport, Plan
from app.learning.service import LearningExtrasService

router = APIRouter(prefix="/api/v1/learning", tags=["learning"], responses=ERROR_RESPONSES)
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0, le=1_000_000)]


def service(request: Request) -> LearningExtrasService:
    return request.app.state.learning


@router.get("/dashboard", response_model=Dashboard)
def dashboard(request: Request, limit: PageLimit = 50, offset: PageOffset = 0) -> Dashboard:
    return service(request).dashboard(token(request), limit=limit, offset=offset)


@router.post("/annotations", response_model=AnnotationView)
def annotate(
    request: Request, body: AnnotationRequest, idempotency_key: IdempotencyKey,
) -> Response:
    return stored_response(service(request).annotate(token(request), body, idempotency_key))


@router.get("/plan", response_model=Plan)
def plan(request: Request, minutes: Annotated[int, Query()] = 10) -> Plan:
    return service(request).plan(token(request), minutes)


@router.get("/export", response_model=LearningExport)
def export(request: Request, limit: PageLimit = 50, offset: PageOffset = 0) -> LearningExport:
    return service(request).export(token(request), limit=limit, offset=offset)
