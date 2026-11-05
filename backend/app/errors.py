"""Stable, secret-free error responses shared by HTTP and domain services."""

from app.schemas import ErrorDetail, ErrorResponse


class ApiError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, field: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.field = field

    def response(self) -> ErrorResponse:
        return ErrorResponse(
            error=ErrorDetail(code=self.code, message=self.message, field=self.field)
        )


def not_found() -> ApiError:
    return ApiError(404, "not_found", "Объект не найден.")
