"""Assessment-only routes; no hints, solutions or immediate attempt endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response

from app.api import ERROR_RESPONSES, IdempotencyKey, stored_response, token
from app.assessments.schemas import (
    AssessmentView,
    DraftRequest,
    FinishRequest,
    PrepareRequest,
    WriterRequest,
)
from app.assessments.service import AssessmentService

router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"], responses=ERROR_RESPONSES)


def service(request: Request) -> AssessmentService:
    return request.app.state.assessments


@router.post("", response_model=AssessmentView)
def prepare(request: Request, body: PrepareRequest, idempotency_key: IdempotencyKey) -> Response:
    return stored_response(service(request).prepare(token(request), body, idempotency_key))


@router.get("/{assessment_id}", response_model=AssessmentView)
def get(
    request: Request, assessment_id: str,
    device: Annotated[UUID | None, Header(alias="X-Assessment-Device")] = None,
) -> AssessmentView:
    return service(request).get(token(request), assessment_id, str(device) if device else None)


@router.post("/{assessment_id}/activate", response_model=AssessmentView)
def activate(
    request: Request, assessment_id: str, body: WriterRequest, idempotency_key: IdempotencyKey
) -> Response:
    return stored_response(service(request).activate(
        token(request), assessment_id, body, idempotency_key
    ))


@router.put("/{assessment_id}/draft", response_model=AssessmentView)
def draft(request: Request, assessment_id: str, body: DraftRequest) -> Response:
    return stored_response(service(request).draft(token(request), assessment_id, body))


@router.post("/{assessment_id}/takeover", response_model=AssessmentView)
def takeover(
    request: Request, assessment_id: str, body: WriterRequest, idempotency_key: IdempotencyKey
) -> Response:
    return stored_response(service(request).takeover(
        token(request), assessment_id, body, idempotency_key
    ))


@router.post("/{assessment_id}/finish", response_model=AssessmentView)
def finish(
    request: Request, assessment_id: str, body: FinishRequest, idempotency_key: IdempotencyKey
) -> Response:
    return stored_response(service(request).finish(
        token(request), assessment_id, body, idempotency_key
    ))
