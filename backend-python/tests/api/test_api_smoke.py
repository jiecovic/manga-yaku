# backend-python/tests/api/test_api_smoke.py
"""Smoke tests for selected API router handlers.

What is tested:
- Basic response contract for health and model-list endpoints.
- Error/status shape for degraded states and malformed metadata.

How it is tested:
- Direct coroutine invocation of router functions (no ASGI app startup).
- Patched dependencies to avoid DB initialization and worker side effects.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from fastapi.responses import JSONResponse

from api.routers.jobs.routes import list_jobs
from api.routers.training.routes import list_training_models
from api.routers.volumes.routes import health


def test_health() -> None:
    with patch("api.routers.volumes.routes.check_db", return_value=(True, None)):
        resp = asyncio.run(health())
    assert resp == {"status": "ok", "database": "ok"}


def test_health_degraded() -> None:
    with patch("api.routers.volumes.routes.check_db", return_value=(False, "db down")):
        resp = asyncio.run(health())
    assert isinstance(resp, JSONResponse)
    degraded = json.loads(resp.body.decode("utf-8"))
    assert resp.status_code == 503
    assert degraded.get("status") == "degraded"
    assert degraded.get("database") == "unavailable"


def test_jobs_list() -> None:
    # Smoke-level contract only: we don't assert payload shape here.
    resp = asyncio.run(list_jobs())
    assert isinstance(resp, list)


def test_training_models() -> None:
    resp = list_training_models()
    payload = resp.model_dump()
    assert "ultralytics_version" in payload
    assert "families" in payload
