import logging
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import log_failure, request_id

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        identifier = uuid4().hex
        scope.setdefault("state", {})["request_id"] = identifier
        context = request_id.set(identifier)
        started = perf_counter()
        status = 500
        method = scope.get("method", "OTHER")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
            method = "OTHER"

        async def send_response(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ] + [(b"x-request-id", identifier.encode("ascii"))]
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception as error:
            status = 500
            log_failure(
                logger,
                "http.unhandled_error",
                error,
                method=method,
                route=getattr(scope.get("route"), "path", "[unmatched]"),
            )
            raise
        finally:
            route = getattr(scope.get("route"), "path", "[unmatched]")
            level = (
                logging.ERROR
                if status >= 500
                else (logging.WARNING if status >= 400 else logging.INFO)
            )
            if route.startswith("/api/health/") and status < 400:
                level = logging.DEBUG
            logger.log(
                level,
                "http.request_completed",
                extra={
                    "event": "http.request_completed",
                    "method": method,
                    "route": route,
                    "status_code": status,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            request_id.reset(context)
