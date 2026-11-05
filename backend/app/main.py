"""FastAPI app factory and the uvicorn entry point ``app.main:app``."""

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.api import router
from app.config import Settings
from app.database import Database
from app.errors import ApiError
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
        yield
        database.dispose()

    application = FastAPI(
        title="ЕГЭ Профиль 2027 — учебное ядро",
        version="0.1.0",
        description=(
            "Первый этап: только гостевая практика, демонстрационные уроки и история. "
            "Это не полный вариант ЕГЭ и не облачный аккаунт. Числа проверяются точно, "
            "без неявного округления. Для изменяющих запросов нужны разрешённый Origin "
            "и X-Requested-With: math-ege. История хранится на сервере; доступна только "
            f"с HttpOnly cookie текущего браузера в течение {config.guest_access_days} дней "
            "с создания гостя. Очистка cookie лишает доступа. Автоматическое удаление "
            "серверных записей и облачное объединение устройств на этом этапе не реализованы."
        ),
        lifespan=lifespan,
    )
    application.state.settings = config
    application.state.database = database
    application.state.service = LearningService(database, config, clock)
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
    return application


app = create_app()
