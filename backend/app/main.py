"""FastAPI app factory and the uvicorn entry point ``app.main:app``."""

import asyncio
import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.accounts.api import router as accounts_router
from app.accounts.service import AccountService
from app.api import require_matching_identity, router
from app.assessments.api import router as assessments_router
from app.assessments.service import AssessmentService
from app.background import DeadlineWorker
from app.config import Settings
from app.database import Database
from app.editor.api import router as editor_router
from app.editor.service import EditorService
from app.errors import ApiError
from app.learning.api import router as learning_router
from app.operations.api import router as operations_router
from app.security import RequestProtectionMiddleware
from app.services import LearningService, utc_now

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None, *, clock: Callable[[], datetime] = utc_now
) -> FastAPI:
    """Create an isolated app. Schema initialization remains explicit/Alembic."""
    config = settings if settings is not None else Settings.from_env()
    database = Database(config)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        worker = DeadlineWorker(
            application.state.assessments, application.state.operation_health, clock=clock,
        )
        application.state.deadline_worker = worker
        await worker.reconcile()
        task = asyncio.create_task(worker.run(), name="assessment-deadlines")
        try:
            yield
        finally:
            worker.stop()
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise
            finally:
                database.dispose()

    application = FastAPI(
        title="ЕГЭ Профиль 2027",
        version="0.2.0",
        description=(
            "Практика, диагностика и учебный пробник первой части. Не полный вариант ЕГЭ "
            "и не прогноз тестового балла. Числа проверяются точно, без неявного округления. "
            "Для изменяющих запросов нужны разрешённый Origin и X-Requested-With: math-ege. "
            "История защищена HttpOnly cookie; аккаунты включаются только после настройки "
            "почты и политики обработки данных. Демоматериалы не прошли независимую "
            "методическую приёмку."
        ),
        lifespan=lifespan,
        dependencies=[Depends(require_matching_identity)],
    )
    application.state.settings = config
    application.state.database = database
    application.state.service = LearningService(database, config, clock)
    application.state.accounts = AccountService(application.state.service)
    application.state.assessments = AssessmentService(application.state.service)
    application.state.learning = application.state.service.extras
    application.state.editor = EditorService(application.state.service)
    application.state.operation_health = application.state.service.operation_health
    application.add_middleware(RequestProtectionMiddleware, settings=config)

    @application.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(exc.response().model_dump(), status_code=exc.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        field = "answer" if any("answer" in item["loc"] for item in errors) else None
        message = "Проверьте поля запроса и их типы."
        if field == "answer":
            message = "Ответ должен быть строкой длиной не более 64 символов."
        error = ApiError(422, "validation_error", message, field)
        return JSONResponse(error.response().model_dump(), status_code=422)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        messages = {404: "Объект не найден.", 405: "Метод запроса не поддерживается."}
        codes = {404: "not_found", 405: "method_not_allowed"}
        error = ApiError(exc.status_code, codes.get(exc.status_code, "http_error"),
                         messages.get(exc.status_code, "Запрос отклонён."))
        return JSONResponse(error.response().model_dump(), status_code=exc.status_code,
                            headers=exc.headers)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # SQLAlchemy exception strings can include bound token digests and DB
        # connection details. Neither request bodies nor exception text is logged.
        logger.error("Database request failed (%s)", type(exc).__name__)
        error = ApiError(503, "database_unavailable", "База данных временно недоступна.")
        return JSONResponse(error.response().model_dump(), status_code=503)

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unexpected API failure (%s)", type(exc).__name__)
        error = ApiError(500, "internal_error", "Внутренняя ошибка. Ответ не был засчитан.")
        return JSONResponse(
            error.response().model_dump(), status_code=500,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    application.include_router(router)
    application.include_router(accounts_router)
    application.include_router(assessments_router)
    application.include_router(learning_router)
    application.include_router(editor_router)
    application.include_router(operations_router)
    return application


app = create_app()
