# backend-python/core/usecases/agent/tool_jobs_shared.py
"""Shared helpers for job-backed agent tools."""

from __future__ import annotations

import hashlib
import json
from typing import Any


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


def _canonical_request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
