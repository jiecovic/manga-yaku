# backend-python/tests/test_api_smoke.py
from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

os.environ["DB_INIT"] = "false"

from app import app


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health(self) -> None:
        resp = self.client.get("/api/health")
        self.assertIn(resp.status_code, (200, 503))
        payload = resp.json()
        self.assertIn("status", payload)
        if resp.status_code == 200:
            self.assertEqual(payload.get("status"), "ok")
            self.assertEqual(payload.get("database"), "ok")
        else:
            self.assertEqual(payload.get("status"), "degraded")
            self.assertEqual(payload.get("database"), "unavailable")

    def test_jobs_list(self) -> None:
        resp = self.client.get("/api/jobs")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_training_models(self) -> None:
        resp = self.client.get("/api/training/models")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("ultralytics_version", payload)
        self.assertIn("families", payload)
