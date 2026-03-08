# backend-python/infra/jobs/operations.py
"""Canonical job enqueue helpers shared by HTTP and agent adapters."""

from __future__ import annotations

from dataclasses import dataclass
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
from infra.jobs.job_modes import (
    BOX_DETECTION_JOB_TYPE,
    OCR_BOX_WORKFLOW_TYPE,
    OCR_PAGE_WORKFLOW_TYPE,
    PAGE_TRANSLATION_WORKFLOW_TYPE,
    PREPARE_DATASET_JOB_TYPE,
    TRAIN_MODEL_JOB_TYPE,
    TRANSLATE_BOX_WORKFLOW_TYPE,
)
from infra.jobs.page_translation_creation import (
    PageTranslationEnqueueDecision,
    create_page_translation_job,
)
from infra.jobs.translate_workflow_creation import create_translate_workflow_with_task
from infra.jobs.utility_workflow_creation import create_persisted_utility_workflow


@dataclass(frozen=True)
class PersistedJobOperationSpec:
    """Canonical metadata for one persisted job-backed operation."""

    operation_id: str
    scope: str
    execution_mode: str
    workflow_type: str
    idempotency_policy: str
    required_fields: tuple[str, ...]
    enqueue_handler: Any
    agent_wait_timeout_seconds: float | None = None
    agent_wait_poll_seconds: float | None = None


def _enqueue_page_translation(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> PageTranslationEnqueueDecision:
    return create_page_translation_job(
        payload=request_payload,
        idempotency_key=idempotency_key,
    )


def _enqueue_box_detection(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    message: str = "Queued",
) -> str:
    _ = idempotency_key
    return create_persisted_utility_workflow(
        workflow_type=BOX_DETECTION_JOB_TYPE,
        request_payload=request_payload,
        message=message,
    )


def _enqueue_prepare_dataset(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    _ = idempotency_key
    return create_persisted_utility_workflow(
        workflow_type=PREPARE_DATASET_JOB_TYPE,
        request_payload=request_payload,
    )


def _enqueue_train_model(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    _ = idempotency_key
    return create_persisted_utility_workflow(
        workflow_type=TRAIN_MODEL_JOB_TYPE,
        request_payload=request_payload,
    )


def _enqueue_ocr_box(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    _ = idempotency_key
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


def _enqueue_ocr_page(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    _ = idempotency_key
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


def _enqueue_translate_box(
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> str:
    _ = idempotency_key
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


PAGE_TRANSLATION_OPERATION = PersistedJobOperationSpec(
    operation_id="translate_active_page",
    scope="page",
    execution_mode="workflow",
    workflow_type=PAGE_TRANSLATION_WORKFLOW_TYPE,
    idempotency_policy="optional_key+active_run_dedupe",
    required_fields=("volumeId", "filename"),
    agent_wait_timeout_seconds=45.0,
    agent_wait_poll_seconds=0.2,
    enqueue_handler=_enqueue_page_translation,
)

BOX_DETECTION_OPERATION = PersistedJobOperationSpec(
    operation_id="detect_text_boxes",
    scope="page",
    execution_mode="workflow",
    workflow_type=BOX_DETECTION_JOB_TYPE,
    idempotency_policy="agent_managed_auto_key",
    required_fields=("volumeId", "filename"),
    agent_wait_timeout_seconds=15.0,
    agent_wait_poll_seconds=0.2,
    enqueue_handler=_enqueue_box_detection,
)

OCR_BOX_OPERATION = PersistedJobOperationSpec(
    operation_id="ocr_text_box",
    scope="box",
    execution_mode="workflow",
    workflow_type=OCR_BOX_WORKFLOW_TYPE,
    idempotency_policy="agent_managed_auto_key",
    required_fields=("profileId", "volumeId", "filename", "x", "y", "width", "height", "boxId"),
    agent_wait_timeout_seconds=20.0,
    agent_wait_poll_seconds=0.2,
    enqueue_handler=_enqueue_ocr_box,
)

OCR_PAGE_OPERATION = PersistedJobOperationSpec(
    operation_id="ocr_page",
    scope="page",
    execution_mode="workflow",
    workflow_type=OCR_PAGE_WORKFLOW_TYPE,
    idempotency_policy="none",
    required_fields=("volumeId", "filename"),
    enqueue_handler=_enqueue_ocr_page,
)

TRANSLATE_BOX_OPERATION = PersistedJobOperationSpec(
    operation_id="translate_box",
    scope="box",
    execution_mode="workflow",
    workflow_type=TRANSLATE_BOX_WORKFLOW_TYPE,
    idempotency_policy="none",
    required_fields=("profileId", "volumeId", "filename", "boxId"),
    enqueue_handler=_enqueue_translate_box,
)

PREPARE_DATASET_OPERATION = PersistedJobOperationSpec(
    operation_id="prepare_dataset",
    scope="dataset",
    execution_mode="workflow",
    workflow_type=PREPARE_DATASET_JOB_TYPE,
    idempotency_policy="none",
    required_fields=("sources",),
    enqueue_handler=_enqueue_prepare_dataset,
)

TRAIN_MODEL_OPERATION = PersistedJobOperationSpec(
    operation_id="train_model",
    scope="model",
    execution_mode="workflow",
    workflow_type=TRAIN_MODEL_JOB_TYPE,
    idempotency_policy="none",
    required_fields=("dataset_id",),
    enqueue_handler=_enqueue_train_model,
)

PERSISTED_JOB_OPERATIONS: dict[str, PersistedJobOperationSpec] = {
    spec.operation_id: spec
    for spec in (
        PAGE_TRANSLATION_OPERATION,
        BOX_DETECTION_OPERATION,
        OCR_BOX_OPERATION,
        OCR_PAGE_OPERATION,
        TRANSLATE_BOX_OPERATION,
        PREPARE_DATASET_OPERATION,
        TRAIN_MODEL_OPERATION,
    )
}


def enqueue_persisted_operation(
    spec: PersistedJobOperationSpec,
    request_payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    message: str | None = None,
) -> Any:
    """Dispatch to one canonical persisted-operation definition."""
    kwargs: dict[str, Any] = {"idempotency_key": idempotency_key}
    if message is not None:
        kwargs["message"] = message
    return spec.enqueue_handler(request_payload, **kwargs)


def enqueue_page_translation_operation(
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> PageTranslationEnqueueDecision:
    """Create or reuse the persisted page-translation workflow."""
    return enqueue_persisted_operation(
        PAGE_TRANSLATION_OPERATION,
        payload,
        idempotency_key=idempotency_key,
    )


def enqueue_box_detection_operation(
    request_payload: dict[str, Any],
    *,
    message: str = "Queued",
) -> str:
    """Create a persisted box-detection workflow from canonical request payload."""
    return enqueue_persisted_operation(
        BOX_DETECTION_OPERATION,
        request_payload=request_payload,
        message=message,
    )


def enqueue_prepare_dataset_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted dataset-preparation workflow."""
    return enqueue_persisted_operation(PREPARE_DATASET_OPERATION, request_payload)


def enqueue_train_model_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted training workflow."""
    return enqueue_persisted_operation(TRAIN_MODEL_OPERATION, request_payload)


def enqueue_ocr_box_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted OCR-box workflow from the shared request payload shape."""
    return enqueue_persisted_operation(OCR_BOX_OPERATION, request_payload)


def enqueue_ocr_page_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted OCR-page workflow from the shared request payload shape."""
    return enqueue_persisted_operation(OCR_PAGE_OPERATION, request_payload)


def enqueue_translate_box_operation(request_payload: dict[str, Any]) -> str:
    """Create a persisted translate-box workflow from the shared request payload shape."""
    return enqueue_persisted_operation(TRANSLATE_BOX_OPERATION, request_payload)


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
