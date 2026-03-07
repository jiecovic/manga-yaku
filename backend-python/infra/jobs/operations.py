# backend-python/infra/jobs/operations.py
"""Canonical job enqueue helpers shared by HTTP and agent adapters."""

from __future__ import annotations

from typing import Any

from core.usecases.ocr.workflow_creation import (
    OcrBoxWorkflowInput,
    OcrPageWorkflowInput,
)
from core.usecases.ocr.workflow_creation import (
    create_ocr_box_workflow as create_persisted_ocr_box_workflow,
)
from core.usecases.ocr.workflow_creation import (
    create_ocr_page_workflow as create_persisted_ocr_page_workflow,
)
from core.usecases.settings.service import get_setting_value
from core.usecases.translation.profiles import get_translation_profile
from infra.jobs.agent_translate_creation import (
    AgentTranslatePageEnqueueDecision,
    create_agent_translate_page_job,
)
from infra.jobs.job_modes import (
    BOX_DETECTION_JOB_TYPE,
    PREPARE_DATASET_JOB_TYPE,
    TRAIN_MODEL_JOB_TYPE,
)
from infra.jobs.translate_workflow_creation import create_translate_workflow_with_task
from infra.jobs.utility_workflow_creation import create_persisted_utility_workflow


def enqueue_agent_translate_page_operation(
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> AgentTranslatePageEnqueueDecision:
    """Create or reuse the persisted agent translate-page workflow."""
    return create_agent_translate_page_job(
        payload=payload,
        idempotency_key=idempotency_key,
    )


def enqueue_box_detection_operation(
    request_payload: dict[str, Any],
    *,
    message: str = "Queued",
) -> str:
    """Create a persisted box-detection workflow from canonical request payload."""
    return create_persisted_utility_workflow(
        workflow_type=BOX_DETECTION_JOB_TYPE,
        request_payload=request_payload,
        message=message,
    )


def enqueue_prepare_dataset_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted dataset-preparation workflow."""
    return create_persisted_utility_workflow(
        workflow_type=PREPARE_DATASET_JOB_TYPE,
        request_payload=request_payload,
    )


def enqueue_train_model_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted training workflow."""
    return create_persisted_utility_workflow(
        workflow_type=TRAIN_MODEL_JOB_TYPE,
        request_payload=request_payload,
    )


def enqueue_ocr_box_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted OCR-box workflow from the shared request payload shape."""
    return create_persisted_ocr_box_workflow(
        OcrBoxWorkflowInput(
            profile_id=str(request_payload.get("profileId") or "").strip(),
            volume_id=str(request_payload.get("volumeId") or "").strip(),
            filename=str(request_payload.get("filename") or "").strip(),
            x=float(request_payload.get("x") or 0.0),
            y=float(request_payload.get("y") or 0.0),
            width=float(request_payload.get("width") or 0.0),
            height=float(request_payload.get("height") or 0.0),
            box_id=int(request_payload.get("boxId") or 0),
            box_order=_optional_int(request_payload.get("boxOrder")),
        )
    )


def enqueue_ocr_page_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted OCR-page workflow from the shared request payload shape."""
    raw_profile_ids = request_payload.get("profileIds")
    profile_ids = list(raw_profile_ids) if isinstance(raw_profile_ids, list) else []
    selected_profile_id = str(request_payload.get("profileId") or "").strip()
    if not selected_profile_id and profile_ids:
        selected_profile_id = str(profile_ids[0] or "").strip()
    return create_persisted_ocr_page_workflow(
        OcrPageWorkflowInput(
            profile_ids=[selected_profile_id] if selected_profile_id else profile_ids,
            volume_id=str(request_payload.get("volumeId") or "").strip(),
            filename=str(request_payload.get("filename") or "").strip(),
            skip_existing=bool(request_payload.get("skipExisting", True)),
        )
    )


def enqueue_translate_box_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted translate-box workflow from the shared request payload shape."""
    profile_id = str(request_payload.get("profileId") or "").strip()
    if not profile_id:
        raise ValueError("profileId is required")
    profile = get_translation_profile(profile_id)
    if not profile.get("enabled", True):
        raise ValueError("Selected translation profile is disabled")

    volume_id = str(request_payload.get("volumeId") or "").strip()
    filename = str(request_payload.get("filename") or "").strip()
    box_id = int(request_payload.get("boxId") or 0)
    if box_id <= 0:
        raise ValueError("boxId is required for translation workflow")

    use_page_context = _resolve_use_page_context(request_payload)
    normalized_request_payload = dict(request_payload)
    normalized_request_payload["profileId"] = profile_id
    normalized_request_payload["volumeId"] = volume_id
    normalized_request_payload["filename"] = filename
    normalized_request_payload["boxId"] = box_id
    normalized_request_payload["usePageContext"] = use_page_context
    return create_translate_workflow_with_task(
        volume_id=volume_id,
        filename=filename,
        request_payload=normalized_request_payload,
        box_id=box_id,
        profile_id=profile_id,
        use_page_context=use_page_context,
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _resolve_use_page_context(request_payload: dict[str, Any]) -> bool:
    raw_value = request_payload.get("usePageContext")
    if raw_value is None:
        configured = get_setting_value("translation.single_box.use_context")
        return bool(configured) if isinstance(configured, bool) else True
    return bool(raw_value)
