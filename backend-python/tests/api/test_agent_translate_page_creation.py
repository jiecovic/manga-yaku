# backend-python/tests/api/test_agent_translate_page_creation.py
"""Unit tests for agent translate-page job creation dedupe/idempotency behavior.

What is tested:
- Active-page dedupe against queued/running in-memory jobs and persisted runs.
- Idempotency-Key replay/conflict/in-progress behavior for page job creation.
- Route-level queueing behavior: only enqueue when a new job is created.

How it is tested:
- Service functions are exercised directly with an isolated in-memory JobStore.
- DB/idempotency lookups are patched to deterministic in-process responses.
- Router endpoint function is called directly with a synthetic Request object.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from api.routers.jobs import routes as jobs_routes
from api.schemas.jobs import CreateAgentTranslatePageJobRequest
from api.services.jobs_creation_service import create_agent_translate_page_job as create_job_record
from infra.jobs.agent_translate_creation import (
    create_agent_translate_page_job as create_shared_job_record,
)
from infra.jobs.store import Job, JobStatus, JobStore


class AgentTranslatePageCreationSharedHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = JobStore()

    def _request(self, **overrides: object) -> CreateAgentTranslatePageJobRequest:
        payload = {
            "volumeId": "vol-a",
            "filename": "001.jpg",
            "detectionProfileId": "yolo_default",
            "ocrProfiles": ["manga_ocr_default", "openai_fast_ocr"],
        }
        payload.update(overrides)
        return CreateAgentTranslatePageJobRequest(**payload)

    def test_reuses_active_memory_job_for_same_page(self) -> None:
        now = self.store.now()
        self.store.add_job(
            Job(
                id="mem-1",
                type="agent_translate_page",
                status=JobStatus.running,
                created_at=now,
                updated_at=now,
                payload={"volumeId": "vol-a", "filename": "001.jpg"},
            )
        )

        result = create_shared_job_record(store=self.store, payload=self._request().model_dump())

        self.assertEqual(result["job_id"], "mem-1")
        self.assertFalse(result["queued"])

    def test_reuses_active_persisted_run_for_same_page(self) -> None:
        with patch(
            "infra.jobs.agent_translate_creation.find_latest_active_workflow_run",
            return_value={"id": "wf-123"},
        ):
            result = create_shared_job_record(store=self.store, payload=self._request().model_dump())

        self.assertEqual(result["job_id"], "wf-123")
        self.assertFalse(result["queued"])

    def test_claimed_idempotency_key_finalizes_new_job(self) -> None:
        with (
            patch(
                "infra.jobs.agent_translate_creation.claim_idempotency_key",
                return_value={"status": "claimed", "resource_id": None},
            ) as claim_mock,
            patch(
                "infra.jobs.agent_translate_creation.finalize_idempotency_key",
                side_effect=lambda **kwargs: kwargs["resource_id"],
            ) as finalize_mock,
        ):
            result = create_shared_job_record(
                store=self.store,
                payload=self._request().model_dump(),
                idempotency_key="page-1-key",
            )

        self.assertTrue(result["queued"])
        self.assertIn(result["job_id"], self.store.jobs)
        claim_mock.assert_called_once()
        finalize_mock.assert_called_once()

    def test_idempotency_key_replay_returns_existing_resource(self) -> None:
        with patch(
            "infra.jobs.agent_translate_creation.claim_idempotency_key",
            return_value={"status": "replay", "resource_id": "wf-777"},
        ):
            result = create_shared_job_record(
                store=self.store,
                payload=self._request().model_dump(),
                idempotency_key="replay-key",
            )

        self.assertEqual(result["job_id"], "wf-777")
        self.assertFalse(result["queued"])
        self.assertEqual(self.store.jobs, {})

    def test_idempotency_key_conflict_returns_conflict_status(self) -> None:
        with (
            patch(
                "infra.jobs.agent_translate_creation.claim_idempotency_key",
                return_value={"status": "conflict", "resource_id": "wf-1"},
            ),
        ):
            result = create_shared_job_record(
                store=self.store,
                payload=self._request().model_dump(),
                idempotency_key="conflict-key",
            )

        self.assertEqual(result["status"], "conflict")
        self.assertIn("conflicts", str(result["detail"]).lower())

    def test_idempotency_key_in_progress_returns_in_progress_status(self) -> None:
        with (
            patch(
                "infra.jobs.agent_translate_creation.claim_idempotency_key",
                return_value={"status": "in_progress", "resource_id": None},
            ),
        ):
            result = create_shared_job_record(
                store=self.store,
                payload=self._request().model_dump(),
                idempotency_key="pending-key",
            )

        self.assertEqual(result["status"], "in_progress")
        self.assertIn("already in progress", str(result["detail"]).lower())

    def test_force_rerun_skips_idempotency_claim(self) -> None:
        with patch("infra.jobs.agent_translate_creation.claim_idempotency_key") as claim_mock:
            result = create_shared_job_record(
                store=self.store,
                payload=self._request(forceRerun=True).model_dump(),
                idempotency_key="ignored-key",
            )

        self.assertTrue(result["queued"])
        claim_mock.assert_not_called()


class AgentTranslatePageCreationServiceTests(unittest.TestCase):
    def test_service_maps_conflict_to_http_409(self) -> None:
        with (
            patch(
                "api.services.jobs_creation_service.create_shared_agent_translate_page_job",
                return_value={
                    "job_id": None,
                    "queued": False,
                    "status": "conflict",
                    "detail": "Idempotency-Key conflicts with a different request payload",
                },
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            create_job_record(
                store=JobStore(),
                req=CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg"),
                idempotency_key="abc",
            )

        self.assertEqual(raised.exception.status_code, 409)

    def test_service_returns_job_id_for_shared_helper_success(self) -> None:
        with patch(
            "api.services.jobs_creation_service.create_shared_agent_translate_page_job",
            return_value={
                "job_id": "job-123",
                "queued": True,
                "status": "queued",
                "detail": None,
            },
        ):
            result = create_job_record(
                store=JobStore(),
                req=CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg"),
            )

        self.assertEqual(result, {"job_id": "job-123", "queued": True})


class AgentTranslatePageRouteTests(unittest.IsolatedAsyncioTestCase):
    def _request_scope(self, *, idempotency_key: str | None = None) -> Request:
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

    async def test_route_skips_queue_put_for_reused_job(self) -> None:
        req = CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg")
        with (
            patch(
                "api.routers.jobs.routes.create_agent_translate_page_job_record",
                return_value={"job_id": "wf-123", "queued": False},
            ) as service_mock,
            patch.object(
                jobs_routes.STORE.queue,
                "put",
                new=AsyncMock(),
            ) as queue_put_mock,
        ):
            resp = await jobs_routes.create_agent_translate_page_job(req, self._request_scope())

        self.assertEqual(resp.jobId, "wf-123")
        queue_put_mock.assert_not_awaited()
        service_mock.assert_called_once()

    async def test_route_enqueues_new_job(self) -> None:
        req = CreateAgentTranslatePageJobRequest(volumeId="vol-a", filename="001.jpg")
        with (
            patch(
                "api.routers.jobs.routes.create_agent_translate_page_job_record",
                return_value={"job_id": "mem-1", "queued": True},
            ) as service_mock,
            patch.object(
                jobs_routes.STORE.queue,
                "put",
                new=AsyncMock(),
            ) as queue_put_mock,
        ):
            resp = await jobs_routes.create_agent_translate_page_job(
                req,
                self._request_scope(idempotency_key="abc"),
            )

        self.assertEqual(resp.jobId, "mem-1")
        queue_put_mock.assert_awaited_once_with("mem-1")
        service_mock.assert_called_once()
