# backend-python/tests/api/test_translate_box_workflow.py
"""Unit tests for persisted translate-box workflow orchestration wiring.

What is tested:
- Translate-box workflow and task creation wiring for queue-backed execution.
- Request/payload shaping before enqueueing downstream worker tasks.
- Guardrails for invalid input and expected HTTP error behavior.

How it is tested:
- Workflow/repository helpers are patched with deterministic return values.
- Router/service helpers are called directly without starting workers.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.routers.jobs.routes import create_translate_box_job
from api.schemas.jobs import CreateTranslateBoxJobRequest
from api.services.jobs_creation_service import create_translate_box_workflow
from api.services.jobs_workflow_helpers import create_translate_workflow_with_task
from fastapi import HTTPException


def test_create_translate_workflow_with_task_creates_single_task() -> None:
    with (
        patch(
            "api.services.jobs_workflow_helpers.create_workflow_run",
            return_value="wf-123",
        ) as create_workflow_run_mock,
        patch("api.services.jobs_workflow_helpers.update_workflow_run") as update_workflow_run_mock,
        patch(
            "api.services.jobs_workflow_helpers.create_task_runs",
            return_value=1,
        ) as create_task_runs_mock,
    ):
        workflow_id = create_translate_workflow_with_task(
            volume_id="vol-a",
            filename="001.jpg",
            request_payload={
                "profileId": "openai_fast_translate",
                "volumeId": "vol-a",
                "filename": "001.jpg",
                "boxId": 5,
                "usePageContext": True,
            },
            box_id=5,
            profile_id="openai_fast_translate",
            use_page_context=True,
        )

    assert workflow_id == "wf-123"
    create_workflow_run_mock.assert_called_once()
    create_task_runs_mock.assert_called_once()
    call_kwargs = create_task_runs_mock.call_args.kwargs
    assert call_kwargs["stage"] == "translate_box"
    assert len(call_kwargs["tasks"]) == 1
    assert call_kwargs["tasks"][0]["box_id"] == 5
    assert call_kwargs["tasks"][0]["profile_id"] == "openai_fast_translate"
    assert call_kwargs["tasks"][0]["input_json"]["use_page_context"] is True
    update_workflow_run_mock.assert_called_once()


@pytest.mark.asyncio
async def test_create_translate_box_job_uses_persisted_workflow() -> None:
    req = CreateTranslateBoxJobRequest(
        profileId="openai_fast_translate",
        volumeId="vol-a",
        filename="001.jpg",
        boxId=9,
        usePageContext=None,
        boxOrder=3,
    )
    with patch(
        "api.routers.jobs.routes.create_translate_box_workflow",
        return_value="wf-xyz",
    ) as create_workflow_mock:
        result = await create_translate_box_job(req)

    assert result.jobId == "wf-xyz"
    create_workflow_mock.assert_called_once_with(req)


def test_create_translate_box_job_builds_translate_task_payload() -> None:
    req = CreateTranslateBoxJobRequest(
        profileId="openai_fast_translate",
        volumeId="vol-a",
        filename="001.jpg",
        boxId=9,
        usePageContext=None,
        boxOrder=3,
    )
    with (
        patch("api.services.jobs_creation_service.get_setting_value", return_value=True),
        patch(
            "api.services.jobs_creation_service.get_translation_profile",
            return_value={"enabled": True},
        ),
        patch(
            "api.services.jobs_creation_service.create_translate_workflow_with_task",
            return_value="wf-xyz",
        ) as create_workflow_mock,
    ):
        workflow_id = create_translate_box_workflow(req)

    assert workflow_id == "wf-xyz"
    create_workflow_mock.assert_called_once()
    kwargs = create_workflow_mock.call_args.kwargs
    assert kwargs["volume_id"] == "vol-a"
    assert kwargs["filename"] == "001.jpg"
    assert kwargs["box_id"] == 9
    assert kwargs["profile_id"] == "openai_fast_translate"
    assert kwargs["use_page_context"] is True
    assert kwargs["request_payload"]["boxOrder"] == 3


def test_create_translate_box_job_rejects_disabled_profile() -> None:
    req = CreateTranslateBoxJobRequest(
        profileId="openai_fast_translate",
        volumeId="vol-a",
        filename="001.jpg",
        boxId=9,
    )
    with (
        patch(
            "api.services.jobs_creation_service.get_translation_profile",
            return_value={"enabled": False},
        ),
        pytest.raises(HTTPException) as raised,
    ):
        create_translate_box_workflow(req)

    assert raised.value.status_code == 400
    assert "disabled" in str(raised.value.detail).lower()
