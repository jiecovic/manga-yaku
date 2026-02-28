# backend-python/infra/http.py
"""Shared HTTP client helpers and request utilities."""

from __future__ import annotations

import os

from fastapi import Request


def cors_headers_for_stream(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin:
        return {}
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173,http://127.0.0.1:5173",
    )
    allowed = [item.strip() for item in raw.split(",") if item.strip()]
    if "*" in allowed or origin in allowed:
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    return {}
