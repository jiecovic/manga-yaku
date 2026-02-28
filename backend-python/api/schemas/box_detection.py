# backend-python/api/schemas/box_detection.py
"""Schemas for box detection profile metadata endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class BoxDetectionProfileInfo(BaseModel):
    """Public box detection profile row shown in provider selectors."""

    id: str
    label: str
    description: str | None = None
    provider: str | None = None
    enabled: bool = True
    classes: list[str] = []
    tasks: list[str] = []

