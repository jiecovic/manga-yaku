"""Typed state and payload models for the agent translate page workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from config import TRANSLATION_SOURCE_LANGUAGE, TRANSLATION_TARGET_LANGUAGE


class WorkflowState(str, Enum):
    queued = "queued"
    detecting_boxes = "detecting_boxes"
    ocr_running = "ocr_running"
    translating = "translating"
    committing = "committing"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class WorkflowEvent(str, Enum):
    start_requested = "start_requested"
    detect_succeeded = "detect_succeeded"
    detect_failed = "detect_failed"
    ocr_succeeded = "ocr_succeeded"
    ocr_failed = "ocr_failed"
    translate_succeeded = "translate_succeeded"
    translate_failed = "translate_failed"
    commit_succeeded = "commit_succeeded"
    commit_failed = "commit_failed"
    cancel_requested = "cancel_requested"


@dataclass(frozen=True)
class AgentTranslatePageRequest:
    volume_id: str
    filename: str
    detection_profile_id: str | None
    source_language: str
    target_language: str
    model_id: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AgentTranslatePageRequest:
        volume_id = str(payload.get("volumeId") or "").strip()
        filename = str(payload.get("filename") or "").strip()
        if not volume_id:
            raise ValueError("volumeId is required")
        if not filename:
            raise ValueError("filename is required")

        raw_profile = payload.get("detectionProfileId")
        detection_profile_id = str(raw_profile).strip() if raw_profile is not None else None
        if detection_profile_id == "":
            detection_profile_id = None

        raw_model_id = payload.get("modelId")
        model_id = str(raw_model_id).strip() if raw_model_id is not None else None
        if model_id == "":
            model_id = None

        return cls(
            volume_id=volume_id,
            filename=filename,
            detection_profile_id=detection_profile_id,
            source_language=str(payload.get("sourceLanguage") or TRANSLATION_SOURCE_LANGUAGE),
            target_language=str(payload.get("targetLanguage") or TRANSLATION_TARGET_LANGUAGE),
            model_id=model_id,
        )


@dataclass(frozen=True)
class AgentTranslateWorkflowSnapshot:
    state: WorkflowState
    stage: str
    progress: int
    message: str
    detection_profile_id: str | None
    detected_boxes: int
    ocr_tasks_total: int = 0
    ocr_tasks_done: int = 0
    updated_boxes: int = 0
    workflow_run_id: str | None = None

    def to_result(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "stage": self.stage,
            "processed": self.ocr_tasks_done or self.detected_boxes,
            "total": self.ocr_tasks_total or self.detected_boxes,
            "updated": self.updated_boxes,
            "orderApplied": False,
            "detectionProfileId": self.detection_profile_id,
            "workflowRunId": self.workflow_run_id,
            "message": self.message,
        }


ProgressCallback = Callable[[AgentTranslateWorkflowSnapshot], None]
CancelCheck = Callable[[], bool]
