"""Smoke tests for key API router handlers without ASGI lifespan startup.

These tests call router handler functions directly and validate baseline
response contracts while avoiding DB/worker startup side effects.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch

from api.routers.jobs import list_jobs
from api.routers.training import list_training_models
from api.routers.volumes import health
from fastapi.responses import JSONResponse


class ApiSmokeTests(unittest.TestCase):
    def test_health(self) -> None:
        with patch("api.routers.volumes.check_db", return_value=(True, None)):
            resp = asyncio.run(health())
        self.assertEqual(resp, {"status": "ok", "database": "ok"})

    def test_health_degraded(self) -> None:
        with patch("api.routers.volumes.check_db", return_value=(False, "db down")):
            resp = asyncio.run(health())
        self.assertIsInstance(resp, JSONResponse)
        degraded = json.loads(resp.body.decode("utf-8"))
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(degraded.get("status"), "degraded")
        self.assertEqual(degraded.get("database"), "unavailable")

    def test_jobs_list(self) -> None:
        resp = asyncio.run(list_jobs())
        self.assertIsInstance(resp, list)

    def test_training_models(self) -> None:
        resp = list_training_models()
        payload = resp.model_dump()
        self.assertIn("ultralytics_version", payload)
        self.assertIn("families", payload)

