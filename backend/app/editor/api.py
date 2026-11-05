"""Private editorial routes. Every read and write requires verified staff and recent MFA."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.accounts import require_staff
from app.editor.schemas import (
    BaseImport,
    BaseList,
    BatchResult,
    ChangeRequest,
    CheckResult,
    CreateRevision,
    EditorActor,
    EditorMeta,
    EditRevision,
    ImportBatch,
    Kind,
    Preview,
    PublishBatch,
    ReviewRequest,
    RevisionList,
    RevisionView,
    SampleReview,
    Status,
    TemplateSample,
    Withdrawal,
    WithdrawRequest,
)
from app.editor.service import EditorService
from app.errors import ApiError
from app.schemas import ErrorResponse
from app.services import StoredResponse

router = APIRouter(
    prefix="/api/v1/editor",
    tags=["editor"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 413, 422, 503)},
)
IdempotencyKey = Annotated[str, Header(min_length=36, max_length=36)]


def _actor(request: Request, *, publish: bool = False) -> EditorActor:
    principal = require_staff(request, publish=publish)
    expected = request.headers.get("X-Editor-Actor")
    if expected is not None and expected != principal.id:
        raise ApiError(
            403,
            "editor_identity_changed",
            "Аккаунт редактора изменился. Сохраните локальный JSON и откройте редактор заново.",
        )
    return EditorActor(id=principal.id, role=principal.role, owner_id=principal.root_guest_id)


def staff(request: Request) -> EditorActor:
    return _actor(request)


def publisher(request: Request) -> EditorActor:
    return _actor(request, publish=True)


Staff = Annotated[EditorActor, Depends(staff)]
Publisher = Annotated[EditorActor, Depends(publisher)]


def service(request: Request) -> EditorService:
    return request.app.state.editor


def token(request: Request) -> str | None:
    return request.cookies.get(request.app.state.settings.cookie_name)


def stored(result: StoredResponse) -> Response:
    return Response(
        content=result.content,
        status_code=result.status_code,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/meta", response_model=EditorMeta)
def meta(request: Request, actor: Staff) -> EditorMeta:
    return service(request).meta(actor)


@router.get("/revisions", response_model=RevisionList)
def revisions(
    request: Request,
    actor: Staff,
    kind: Kind | None = None,
    status: Status | None = None,
    q: Annotated[str, Query(max_length=200)] = "",
    content_id: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> RevisionList:
    return service(request).list_revisions(
        actor,
        kind=kind,
        status=status,
        q=q,
        content_id=content_id,
        limit=limit,
        offset=offset,
    )


@router.post("/revisions", response_model=RevisionView)
def create(
    request: Request,
    actor: Staff,
    body: CreateRevision,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(service(request).create(token(request), actor, body, idempotency_key))


@router.get("/revisions/{identifier}", response_model=RevisionView)
def revision(request: Request, actor: Staff, identifier: str) -> RevisionView:
    return service(request).get(actor, identifier)


@router.put("/revisions/{identifier}", response_model=RevisionView)
def edit(
    request: Request,
    actor: Staff,
    identifier: str,
    body: EditRevision,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(service(request).edit(token(request), actor, identifier, body, idempotency_key))


@router.post("/revisions/{identifier}/fork", response_model=RevisionView)
def fork(
    request: Request,
    actor: Staff,
    identifier: str,
    body: ChangeRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(service(request).fork(token(request), actor, identifier, body, idempotency_key))


@router.post("/revisions/{identifier}/submit", response_model=RevisionView)
def submit(
    request: Request,
    actor: Staff,
    identifier: str,
    body: ReviewRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).transition(
            token(request),
            actor,
            identifier,
            "submit",
            body,
            idempotency_key,
        )
    )


@router.post("/revisions/{identifier}/return_to_draft", response_model=RevisionView)
def return_to_draft(
    request: Request,
    actor: Staff,
    identifier: str,
    body: ReviewRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).transition(
            token(request),
            actor,
            identifier,
            "return_to_draft",
            body,
            idempotency_key,
        )
    )


@router.post("/revisions/{identifier}/approve", response_model=RevisionView)
def approve(
    request: Request,
    actor: Staff,
    identifier: str,
    body: ReviewRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).transition(
            token(request),
            actor,
            identifier,
            "approve",
            body,
            idempotency_key,
        )
    )


@router.post("/revisions/{identifier}/publish", response_model=RevisionView)
def publish(
    request: Request,
    actor: Publisher,
    identifier: str,
    body: ChangeRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).publish(token(request), actor, identifier, body, idempotency_key)
    )


@router.post("/publish", response_model=BatchResult)
def publish_batch(
    request: Request,
    actor: Publisher,
    body: PublishBatch,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(service(request).publish_batch(token(request), actor, body, idempotency_key))


@router.post("/revisions/{identifier}/archive", response_model=RevisionView)
def archive(
    request: Request,
    actor: Staff,
    identifier: str,
    body: ChangeRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).archive(token(request), actor, identifier, body, idempotency_key)
    )


@router.post("/tasks/{content_id}/withdraw", response_model=Withdrawal)
def withdraw(
    request: Request,
    actor: Publisher,
    content_id: str,
    body: WithdrawRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).withdraw(token(request), actor, content_id, body, idempotency_key)
    )


@router.post("/import", response_model=BatchResult)
def import_batch(
    request: Request,
    actor: Staff,
    body: ImportBatch,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(service(request).import_batch(token(request), actor, body, idempotency_key))


@router.get("/export", response_model=ImportBatch)
def export(
    request: Request,
    actor: Staff,
    ids: Annotated[list[str], Query(min_length=1, max_length=10)],
) -> ImportBatch:
    return service(request).export(actor, ids)


@router.post("/preview", response_model=Preview)
def preview(request: Request, actor: Staff, body: CreateRevision) -> Preview:
    return service(request).preview(actor, body)


@router.get("/base", response_model=BaseList)
def base(
    request: Request,
    actor: Staff,
    kind: Kind = "task",
    q: Annotated[str, Query(max_length=200)] = "",
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> BaseList:
    return service(request).base_list(actor, kind, q, offset)


@router.post("/base/{kind}/{content_id}", response_model=RevisionView)
def import_base(
    request: Request,
    actor: Staff,
    kind: Kind,
    content_id: str,
    body: BaseImport,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).import_base(token(request), actor, kind, content_id, body, idempotency_key)
    )


@router.get("/revisions/{identifier}/sample", response_model=TemplateSample)
def sample(
    request: Request,
    actor: Staff,
    identifier: str,
    seed: Annotated[int, Query(ge=0, le=2**32 - 1)],
) -> TemplateSample:
    return service(request).sample(actor, identifier, seed)


@router.post("/revisions/{identifier}/checks", response_model=CheckResult)
def checks(
    request: Request,
    actor: Staff,
    identifier: str,
    body: ChangeRequest,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).run_checks(token(request), actor, identifier, body, idempotency_key)
    )


@router.post("/revisions/{identifier}/samples", response_model=RevisionView)
def review_sample(
    request: Request,
    actor: Staff,
    identifier: str,
    body: SampleReview,
    idempotency_key: IdempotencyKey,
) -> Response:
    return stored(
        service(request).review_sample(token(request), actor, identifier, body, idempotency_key)
    )
