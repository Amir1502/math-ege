"""Same-origin writes, bounded ASGI bodies and private response headers."""

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings
from app.errors import ApiError


class RequestProtectionMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secure_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                if scope["path"].startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
                    headers["Vary"] = "Cookie"
                if self.settings.cookie_secure:
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        async def reject(error: ApiError) -> None:
            response = JSONResponse(error.response().model_dump(), status_code=error.status_code)
            await response(scope, receive, secure_send)

        headers = Headers(scope=scope)
        mutating = scope["method"] not in {"GET", "HEAD", "OPTIONS"}
        if mutating:
            if headers.getlist("x-requested-with") != ["math-ege"]:
                await reject(ApiError(
                    403, "request_forbidden", "Нужен заголовок X-Requested-With: math-ege."
                ))
                return
            origins = headers.getlist("origin")
            if len(origins) != 1 or origins[0] not in self.settings.allowed_origins:
                await reject(ApiError(403, "origin_forbidden", "Источник запроса не разрешён."))
                return
            if headers.get("sec-fetch-site") == "cross-site":
                await reject(ApiError(403, "origin_forbidden", "Межсайтовый запрос не разрешён."))
                return
            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                await reject(ApiError(
                    415, "unsupported_media_type", "Передайте тело application/json."
                ))
                return

        lengths = headers.getlist("content-length")
        if len(lengths) > 1 or (lengths and not lengths[0].isascii()) or (
            lengths and not lengths[0].isdigit()
        ):
            await reject(ApiError(400, "invalid_content_length", "Неверная длина тела запроса."))
            return
        if lengths:
            declared = lengths[0].lstrip("0") or "0"
            maximum = str(self.settings.max_request_bytes)
            if len(declared) > len(maximum) or (
                len(declared) == len(maximum) and declared > maximum
            ):
                await reject(ApiError(
                    413, "request_too_large", "Превышен предел размера тела запроса."
                ))
                return

        # Buffer only a bounded body before the application reads or mutates
        # anything. This also limits chunked requests without Content-Length.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.settings.max_request_bytes:
                await reject(ApiError(
                    413, "request_too_large", "Превышен предел размера тела запроса."
                ))
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, secure_send)
