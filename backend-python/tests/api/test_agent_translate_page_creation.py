# backend-python/tests/api/test_agent_translate_page_creation.py
"""Unit tests for agent translate-page job creation dedupe/idempotency behavior."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.routers.jobs import routes as jobs_routes
from api.schemas.jobs import CreateAgentTranslatePageJobRequest
from api.services.jobs_creation_service import create_agent_translate_page_job as create_job_record
from fastapi import HTTPException
from infra.jobs.agent_translate_creation import (
    create_agent_translate_page_job as create_shared_job_record,
)
from starlette.requests import Request


def _request(**overrides: object) -> CreateAgentTranslatePageJobRequest:
    payload = {
        "volumeId": "vol-a",
        "filename": "001.jpg",
        "detectionProfileId": "yolo_default",
        "ocrProfiles": ["manga_ocr_default", "openai_fast_ocr"],
    }
    payload.update(overrides)
    return CreateAgentTranslatePageJobRequest(**payload)


def _request_scope(*, idempotency_key: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if idempotency_key:
        headers.append((b"idempotency-key", idempotency_key.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/jobs/agent_translate_page",
        "headers": headers,
    }
    return Request(scope)


def test_reuses_active_persisted_run_for_same_page() -> None:
    with patch(
        "infra.jobs.agent_translate_creation.find_latest_active_workflow_run",
        return_value={"id": "wf-123"},
    ):
        result = create_shared_job_record(payload=_request().model_dump())

    assert result["job_id"] == "wf-123"
    assert result["queued"] is False


def test_claimed_idempotency_key_finalizes_new_job() -> None:
    with (
        patch(
            "infra.jobs.agent_translate_creation.claim_idempotency_key",
            return_value={"status": "claimed", "resource_id": None},
        ) as claim_mock,
        patch(
            "infra.jobs.agent_translate_creation.finalize_idempotency_key",
            side_effect=lambda **kwargs: kwargs["resource_id"],
        ) as finalize_mock,
        patch(
            "infra.jobs.agent_translate_creation.create_workflow_run_with_task",
            return_value="wf-new-1",
        ) as create_mock,
    ):
        result = create_shared_job_record(
            payload=_request().model_dump(),
            idempotency_key="page-1-key",
        )

    assert result["queued"] is True
    assert result["job_id"] == "wf-new-1"
    claim_mock.assert_called_once()
    finalize_mock.assert_called_once()
    create_mock.assert_called_once()


def test_cleans_up_new_workflow_when_idempotency_finalize_conflicts() -> None:
    with (
        patch(
            "infra.jobs.agent_translate_creation.claim_idempotency_key",
            return_value={"status": "claimed", "resource_id": None},
        ),
        patch(
            "infra.jobs.agent_translate_creation.create_workflow_run_with_task",
            return_value="wf-temp-1",
        ),
        patch(
            "infra.jobs.agent_translate_creation.finalize_idempotency_key",
            side_effect=ValueError("conflict"),
        ),
        patch("infra.jobs.agent_translate_creation.delete_workflow_run") as delete_mock,
    ):
        result = create_shared_job_record(
            payload=_request().model_dump(),
            idempotency_key="page-1-key",
        )

    assert result["status"] == "conflict"
    delete_mock.assert_called_once_with("wf-temp-1")


def test_idempotency_key_replay_returns_existing_resource() -> None:
    with patch(
        "infra.jobs.agent_translate_creation.claim_idempotency_key",
        return_value={"status": "replay", "resource_id": "wf-777"},
    ):
        result = create_shared_job_record(
            payload=_request().model_dump(),
            idempotency_key="replay-key",
        )

    assert result["job_id"] == "wf-777"
    assert result["queued"] is False


def test_idempotency_key_conflict_returns_conflict_status() -> None:
    with patch(
        "infra.jobs.agent_translate_creation.claim_idempotency_key",
        return_value={"status": "conflict", "resource_id": "wf-1"},
    ):
        result = create_shared_job_record(
            payload=_request().model_dump(),
            idempotency_key="conflict-key",
        )

    assert result["status"] == "conflict"
    assert "conflicts" in str(result["detail"]).lower()


def test_idempotency_key_in_progress_returns_in_progress_status() -> None:
    with patch(
        "infra.jobs.agent_translate_creation.claim_idempotency_key",
        return_value={"status": "in_progress", "resource_id": None},
    ):
        result = create_shared_job_record(
            payload=_request().model_dump(),
            idempotency_key="pending-key",
        )

    assert result["status"] == "in_progress"
    assert "already in progress" in str(result["detail"]).lower()


def test_force_rerun_skips_idempotency_claim() -> None:
    with (
        patch("infra.jobs.agent_translate_creation.claim_idempotency_key") as claim_mock,
        patch(
            "infra.jobs.agent_translate_creation.create_workflow_run_with_task",
            return_value="wf-force-1",
        ),
    ):
        result = create_shared_job_record(
            payload=_request(forceRerun=True).model_dump(),
            idempotency_key="ignored-key",
        )

    assert result["queued"] is True
    claim_mock.assert_not_called()


def test_service_maps_conflict_to_http_409() -> None:
    with (
        patch(
            "api.services.jobs_creation_service.enqueue_agent_translate_page_operation",
            return_value={
                "job_id": None,
                "queued": False,
                "status": "conflict",
                "detail": "Idempotency-Key conflicts with a different request payload",
            },
        ),
        pytest.raises(HTTPException) as raised,
    ):
        create_job_record(
            req=CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg"),
            idempotency_key="abc",
        )

    assert raised.value.status_code == 409


def test_service_returns_job_id_for_shared_helper_success() -> None:
    with patch(
        "api.services.jobs_creation_service.enqueue_agent_translate_page_operation",
        return_value={
            "job_id": "job-123",
            "queued": True,
            "status": "queued",
            "detail": None,
        },
    ):
        result = create_job_record(
            req=CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg"),
        )

    assert result == {"job_id": "job-123", "queued": True}


@pytest.mark.asyncio
async def test_route_skips_queue_put_for_reused_job() -> None:
    req = CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg")
    with (
        patch(
            "api.routers.jobs.routes.create_agent_translate_page_job_record",
            return_value={"job_id": "wf-123", "queued": False},
        ) as service_mock,
        patch("api.routers.jobs.routes._notify_jobs_changed") as notify_mock,
    ):
        resp = await jobs_routes.create_agent_translate_page_job(req, _request_scope())

    assert resp.jobId == "wf-123"
    service_mock.assert_called_once()
    notify_mock.assert_called_once()


@pytest.mark.asyncio
async def test_route_returns_new_job_id_without_manual_queue_step() -> None:
    req = CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg")
    with (
        patch(
            "api.routers.jobs.routes.create_agent_translate_page_job_record",
            return_value={"job_id": "wf-new-1", "queued": True},
        ) as service_mock,
        patch("api.routers.jobs.routes._notify_jobs_changed") as notify_mock,
    ):
        resp = await jobs_routes.create_agent_translate_page_job(
            req,
            _request_scope(idempotency_key="abc"),
        )

    assert resp.jobId == "wf-new-1"
    service_mock.assert_called_once()
    notify_mock.assert_called_once()
