# backend-python/tests/api/test_missing_box_detection_job_route.py
"""Route tests for queued LLM missing-box detection job creation."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from api.routers.jobs import routes as jobs_routes
from api.schemas.jobs import CreateMissingBoxDetectionJobRequest
from infra.jobs.job_modes import MISSING_BOX_DETECTION_JOB_TYPE


class MissingBoxDetectionRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_enqueues_missing_box_detection_job(self) -> None:
        req = CreateMissingBoxDetectionJobRequest(volumeId="vol-a", filename="001.jpg")

        with (
            patch(
                "api.routers.jobs.routes.enqueue_memory_job",
                return_value="mem-missing-1",
            ) as enqueue_mock,
            patch.object(
                jobs_routes.STORE.queue,
                "put",
                new=AsyncMock(),
            ) as queue_put_mock,
        ):
            response = await jobs_routes.create_missing_box_detection_job(req)

        self.assertEqual(response.jobId, "mem-missing-1")
        queue_put_mock.assert_awaited_once_with("mem-missing-1")
        enqueue_mock.assert_called_once()
        kwargs = enqueue_mock.call_args.kwargs
        self.assertEqual(kwargs["job_type"], MISSING_BOX_DETECTION_JOB_TYPE)
        self.assertEqual(kwargs["payload"]["volumeId"], "vol-a")
        self.assertEqual(kwargs["payload"]["filename"], "001.jpg")
