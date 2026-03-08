# backend-python/infra/jobs/page_translation_creation.py
"""Shared job-creation helpers for the page-translation workflow."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, TypedDict

from infra.db.idempotency_store import (
    claim_idempotency_key,
    finalize_idempotency_key,
    release_idempotency_claim,
)
from infra.db.workflow_store import (
    create_workflow_run_with_task,
    delete_workflow_run,
    find_latest_active_workflow_run,
)
from infra.jobs.job_modes import PAGE_TRANSLATION_WORKFLOW_TYPE
from infra.logging.correlation import append_correlation

logger = logging.getLogger(__name__)


class PageTranslationEnqueueDecision(TypedDict):
    """Shared enqueue decision for the page-translation workflow."""

    job_id: str | None
    queued: bool
    status: str
    detail: str | None


def _normalize_optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_profile_ids(raw_profile_ids: list[str] | None) -> list[str] | None:
    if not isinstance(raw_profile_ids, list):
        return None
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_profile_ids:
        profile_id = str(raw or "").strip()
        if not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        out.append(profile_id)
    return out or None


def normalize_page_translation_payload(raw_payload: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "volumeId": str(raw_payload.get("volumeId") or "").strip(),
        "filename": str(raw_payload.get("filename") or "").strip(),
        "detectionProfileId": _normalize_optional_str(raw_payload.get("detectionProfileId")),
        "preserveExistingBoxes": bool(raw_payload.get("preserveExistingBoxes", True)),
        "ocrProfiles": _normalize_profile_ids(raw_payload.get("ocrProfiles")),
        "sourceLanguage": _normalize_optional_str(raw_payload.get("sourceLanguage")),
        "targetLanguage": _normalize_optional_str(raw_payload.get("targetLanguage")),
        "modelId": _normalize_optional_str(raw_payload.get("modelId")),
        "forceRerun": bool(raw_payload.get("forceRerun")),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _idempotency_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_idempotency_key(raw_key: str | None) -> str | None:
    key = str(raw_key or "").strip()
    return key or None


def _find_active_page_translation_run_id(
    *,
    volume_id: str,
    filename: str,
) -> str | None:
    try:
        run = find_latest_active_workflow_run(
            workflow_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
            volume_id=volume_id,
            filename=filename,
        )
    except Exception:
        logger.exception(
            append_correlation(
                "Failed to inspect active persisted page-translation workflow",
                {
                    "component": "jobs.creation.page_translation",
                    "volume_id": volume_id,
                    "filename": filename,
                },
            )
        )
        return None
    if not isinstance(run, dict):
        return None
    run_id = str(run.get("id") or "").strip()
    return run_id or None


def _create_page_translation_workflow(payload: dict[str, Any]) -> str:
    volume_id = str(payload.get("volumeId") or "").strip()
    filename = str(payload.get("filename") or "").strip()
    return create_workflow_run_with_task(
        workflow_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
        volume_id=volume_id,
        filename=filename,
        state="queued",
        status="queued",
        result_json={
            "request": dict(payload),
            "progress": 0,
            "message": "Queued",
        },
        stage=PAGE_TRANSLATION_WORKFLOW_TYPE,
        task_status="queued",
        input_json=dict(payload),
    )


def create_page_translation_job(
    *,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> PageTranslationEnqueueDecision:
    """Create or reuse a page-translation job without API-layer dependencies."""

    normalized_payload = normalize_page_translation_payload(payload)
    volume_id = str(normalized_payload.get("volumeId") or "").strip()
    filename = str(normalized_payload.get("filename") or "").strip()
    if not volume_id or not filename:
        return {
            "job_id": None,
            "queued": False,
            "status": "invalid",
            "detail": "volumeId and filename are required",
        }

    active_run_id = _find_active_page_translation_run_id(
        volume_id=volume_id,
        filename=filename,
    )
    if active_run_id:
        return {
            "job_id": active_run_id,
            "queued": False,
            "status": "reused_active",
            "detail": None,
        }

    force_rerun = bool(normalized_payload.get("forceRerun"))
    normalized_idempotency_key = _normalize_idempotency_key(idempotency_key)
    request_hash = _idempotency_request_hash(normalized_payload)
    claimed = False
    if normalized_idempotency_key and not force_rerun:
        claim = claim_idempotency_key(
            job_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
            idempotency_key=normalized_idempotency_key,
            request_hash=request_hash,
        )
        claim_status = str(claim.get("status") or "")
        if claim_status == "replay":
            resource_id = str(claim.get("resource_id") or "").strip()
            return {
                "job_id": resource_id or None,
                "queued": False,
                "status": "replay",
                "detail": None,
            }
        if claim_status == "conflict":
            return {
                "job_id": None,
                "queued": False,
                "status": "conflict",
                "detail": "Idempotency-Key conflicts with a different request payload",
            }
        if claim_status == "in_progress":
            return {
                "job_id": None,
                "queued": False,
                "status": "in_progress",
                "detail": "Idempotency-Key request is already in progress",
            }
        claimed = claim_status == "claimed"

    try:
        job_id = _create_page_translation_workflow(normalized_payload)
    except Exception as exc:
        if normalized_idempotency_key and claimed:
            release_idempotency_claim(
                job_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
                idempotency_key=normalized_idempotency_key,
                request_hash=request_hash,
            )
        return {
            "job_id": None,
            "queued": False,
            "status": "error",
            "detail": str(exc).strip() or "Failed to enqueue page-translate job",
        }

    if normalized_idempotency_key and claimed:
        try:
            resource_id = finalize_idempotency_key(
                job_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
                idempotency_key=normalized_idempotency_key,
                request_hash=request_hash,
                resource_id=job_id,
            )
        except ValueError:
            delete_workflow_run(job_id)
            return {
                "job_id": None,
                "queued": False,
                "status": "conflict",
                "detail": "Idempotency-Key conflicts with a different request payload",
            }
        if resource_id != job_id:
            delete_workflow_run(job_id)
            return {
                "job_id": resource_id,
                "queued": False,
                "status": "replay",
                "detail": None,
            }

    return {
        "job_id": job_id,
        "queued": True,
        "status": "queued",
        "detail": None,
    }
