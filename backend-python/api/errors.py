# backend-python/api/errors.py
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)


def _error_payload(
    *,
    code: str,
    message: str,
    detail: Any,
) -> dict:
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
        return JSONResponse(status_code=exc.status_code, content=payload)

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
        if isinstance(exc, OperationalError):
            logger.exception("Database unavailable", exc_info=exc)
            payload = _error_payload(
                code="db_unavailable",
                message="Database unavailable",
                detail="Database unavailable. Check DATABASE_URL and that Postgres is running.",
            )
            return JSONResponse(status_code=503, content=payload)
        logger.exception("Unhandled exception", exc_info=exc)
        payload = _error_payload(
            code="internal_error",
            message="Internal server error",
            detail="Internal server error",
        )
        return JSONResponse(status_code=500, content=payload)
