# backend-python/tests/api/test_jobs_resume_route.py
"""Route tests for agent job resume creation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from api.routers.jobs import routes as jobs_routes
from infra.jobs.job_modes import AGENT_WORKFLOW_TYPE


class ResumeJobRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_resume_route_uses_atomic_runtime_helper(self) -> None:
        with (
            patch(
                "api.routers.jobs.routes.get_resume_agent_payload",
                return_value={"volumeId": "vol-a", "filename": "001.jpg"},
            ) as payload_mock,
            patch(
                "api.routers.jobs.routes.create_and_enqueue_memory_job",
                return_value="mem-resume-1",
            ) as create_mock,
        ):
            response = await jobs_routes.resume_job("wf-123")

        self.assertEqual(response.jobId, "mem-resume-1")
        payload_mock.assert_called_once_with(job_id="wf-123", store=jobs_routes.STORE)
        create_mock.assert_called_once_with(
            job_type=AGENT_WORKFLOW_TYPE,
            payload={"volumeId": "vol-a", "filename": "001.jpg"},
            progress=0,
            message="Queued (resume)",
        )
