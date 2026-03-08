# backend-python/core/usecases/agent/tool_jobs_shared.py
"""Shared helpers for job-backed agent tools."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from infra.jobs.workflow_runtime import wait_for_workflow_snapshot


def build_auto_idempotency_key(*, namespace: str, payload: dict[str, Any]) -> tuple[str, str]:
    """Return a stable idempotency key and full request hash."""
    request_hash = _canonical_request_hash(payload)
    return f"{namespace}:{request_hash[:32]}", request_hash


def normalize_claim_status(status: str) -> str:
    """Map DB idempotency claim states onto the tool-facing states."""
    normalized = str(status or "").strip().lower()
    if normalized == "claimed":
        return "new"
    if normalized in {"replay", "in_progress", "conflict"}:
        return normalized
    return "new"


def build_box_revision(box: dict[str, Any]) -> dict[str, Any]:
    """Return a stable OCR box snapshot for idempotency hashing."""
    return {
        "id": int(box.get("id") or 0),
        "orderIndex": int(box.get("orderIndex") or 0),
        "x": round(float(box.get("x") or 0.0), 3),
        "y": round(float(box.get("y") or 0.0), 3),
        "width": round(float(box.get("width") or 0.0), 3),
        "height": round(float(box.get("height") or 0.0), 3),
        "text": str(box.get("text") or "").strip(),
        "translation": str(box.get("translation") or "").strip(),
        "note": str(box.get("note") or "").strip(),
    }


@dataclass(frozen=True)
class AgentWorkflowObservation:
    """Normalized workflow wait result for agent-facing job tools."""

    workflow_run_id: str
    workflow_status: str
    result_json: dict[str, Any]
    error_message: str | None
    found: bool
    wait_error: str | None = None

    @property
    def active(self) -> bool:
        """Return whether the workflow is still queued or running."""
        return self.workflow_status in {"queued", "running"}

    @property
    def failed(self) -> bool:
        """Return whether the workflow reached failed status."""
        return self.workflow_status == "failed"

    @property
    def canceled(self) -> bool:
        """Return whether the workflow reached canceled status."""
        return self.workflow_status == "canceled"


def wait_for_agent_workflow(
    *,
    workflow_run_id: str,
    timeout_seconds: float,
    poll_seconds: float,
    wait_error_message: str,
) -> AgentWorkflowObservation:
    """Poll a workflow for an agent tool and return a normalized observation."""
    try:
        snapshot = wait_for_workflow_snapshot(
            workflow_run_id,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
    except Exception as exc:
        error_text = str(exc).strip() or wait_error_message
        return AgentWorkflowObservation(
            workflow_run_id=workflow_run_id,
            workflow_status="wait_error",
            result_json={},
            error_message=error_text,
            found=False,
            wait_error=error_text,
        )

    run_error = None
    if isinstance(snapshot.run, dict):
        run_error = str(snapshot.run.get("error_message") or "").strip() or None
    result_json = snapshot.result_json
    result_error = str(result_json.get("error_message") or "").strip() or None
    return AgentWorkflowObservation(
        workflow_run_id=snapshot.workflow_run_id or workflow_run_id,
        workflow_status=snapshot.status or "missing",
        result_json=result_json,
        error_message=result_error or run_error,
        found=snapshot.found,
    )


def _canonical_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
