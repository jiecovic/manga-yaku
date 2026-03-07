# backend-python/api/errors.py
"""Global API error handling for FastAPI routes.

The handlers in this module shape outbound HTTP JSON error responses returned
by backend endpoints to API clients (frontend, curl, scripts, etc.).

Responsibilities:
- Normalize error responses into a stable payload shape:
  `{"detail": ..., "error": {"code": str, "message": str, "details"?: ...}}`
- Map framework/domain exceptions to consistent HTTP statuses:
  - `HTTPException` -> passthrough status with `http_error`
  - `RequestValidationError` -> `422` with `validation_error`
  - `OperationalError` (SQLAlchemy) -> `503` with `db_unavailable`
  - any other uncaught exception -> `500` with `internal_error`

Why this exists:
- Keeps frontend error handling simple and predictable.
- Prevents leaking raw exception internals to clients.
- Provides explicit user-facing messaging for common infra failures (DB down).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from infra.logging.correlation import append_correlation
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


def _error_payload(
    *,
    code: str,
    message: str,
    detail: Any,
) -> dict[str, Any]:
    payload = {
        "detail": detail,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if detail is not None and detail != message:
        payload["error"]["details"] = detail
    return payload


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request,
        exc: HTTPException,
    ) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Request failed"
        payload = _error_payload(code="http_error", message=message, detail=detail)
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        detail = exc.errors()
        payload = _error_payload(code="validation_error", message="Validation error", detail=detail)
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_corr = {
            "component": "api.errors",
            "method": request.method,
            "path": request.url.path,
        }
        if isinstance(exc, OperationalError):
            logger.exception(
                append_correlation(
                    "Database unavailable",
                    request_corr,
                ),
                exc_info=exc,
            )
            payload = _error_payload(
                code="db_unavailable",
                message="Database unavailable",
                detail="Database unavailable. Check DATABASE_URL and that Postgres is running.",
            )
            return JSONResponse(status_code=503, content=payload)
        logger.exception(
            append_correlation(
                "Unhandled exception",
                request_corr,
            ),
            exc_info=exc,
        )
        payload = _error_payload(
            code="internal_error",
            message="Internal server error",
            detail="Internal server error",
        )
        return JSONResponse(status_code=500, content=payload)
