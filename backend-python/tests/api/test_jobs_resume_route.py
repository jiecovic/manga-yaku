# backend-python/tests/api/test_jobs_resume_route.py
"""Route tests for agent job resume creation."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.routers.jobs import routes as jobs_routes


@pytest.mark.asyncio
async def test_resume_route_reuses_shared_agent_creation_helper() -> None:
    with (
        patch(
            "api.routers.jobs.routes.get_resume_agent_payload",
            return_value={
                "volumeId": "vol-a",
                "filename": "001.jpg",
                "sourceLanguage": "ja",
            },
        ) as payload_mock,
        patch(
            "api.routers.jobs.routes.create_agent_translate_page_job_record",
            return_value={"job_id": "wf-resume-1", "queued": True},
        ) as create_mock,
    ):
        response = await jobs_routes.resume_job("wf-123")

    assert response.jobId == "wf-resume-1"
    payload_mock.assert_called_once_with(job_id="wf-123", store=jobs_routes.STORE)
    create_mock.assert_called_once()
    called_req = create_mock.call_args.kwargs["req"]
    assert called_req.volumeId == "vol-a"
    assert called_req.filename == "001.jpg"
    assert called_req.sourceLanguage == "ja"
    assert create_mock.call_args.kwargs["store"] is jobs_routes.STORE
