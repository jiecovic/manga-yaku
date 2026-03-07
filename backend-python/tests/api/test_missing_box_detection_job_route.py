# backend-python/tests/api/test_missing_box_detection_job_route.py
"""Route tests for persisted LLM missing-box detection workflow creation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from api.routers.jobs import routes as jobs_routes
from api.schemas.jobs import CreateMissingBoxDetectionJobRequest


class MissingBoxDetectionRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_creates_missing_box_detection_workflow(self) -> None:
        req = CreateMissingBoxDetectionJobRequest(volumeId="vol-a", filename="001.jpg")

        with (
            patch(
                "api.routers.jobs.routes.create_missing_box_detection_workflow",
                return_value="wf-missing-1",
            ) as create_mock,
        ):
            response = await jobs_routes.create_missing_box_detection_job(req)

        self.assertEqual(response.jobId, "wf-missing-1")
        create_mock.assert_called_once_with(req)
