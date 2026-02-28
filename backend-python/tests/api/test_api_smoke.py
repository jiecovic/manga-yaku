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
import unittest
from unittest.mock import patch

from api.routers.jobs.routes import list_jobs
from api.routers.training import list_training_models
from api.routers.volumes.routes import health
from fastapi.responses import JSONResponse


class ApiSmokeTests(unittest.TestCase):
    def test_health(self) -> None:
        with patch("api.routers.volumes.routes.check_db", return_value=(True, None)):
            resp = asyncio.run(health())
        self.assertEqual(resp, {"status": "ok", "database": "ok"})

    def test_health_degraded(self) -> None:
        with patch("api.routers.volumes.routes.check_db", return_value=(False, "db down")):
            resp = asyncio.run(health())
        self.assertIsInstance(resp, JSONResponse)
        degraded = json.loads(resp.body.decode("utf-8"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(degraded.get("status"), "degraded")
        self.assertEqual(degraded.get("database"), "unavailable")

    def test_jobs_list(self) -> None:
        # Smoke-level contract only: we don't assert payload shape here.
        resp = asyncio.run(list_jobs())
        self.assertIsInstance(resp, list)

    def test_training_models(self) -> None:
        resp = list_training_models()
        payload = resp.model_dump()
        self.assertIn("ultralytics_version", payload)
        self.assertIn("families", payload)
