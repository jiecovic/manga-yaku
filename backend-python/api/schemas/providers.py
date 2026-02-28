# backend-python/api/schemas/providers.py
"""Schemas for OCR and translation provider listing endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class OcrProvider(BaseModel):
    """Public OCR provider/profile exposed to the frontend."""

    id: str
    label: str
    description: str | None = None
    kind: str = "local"
    enabled: bool = True


class TranslationProvider(BaseModel):
    """Public translation provider/profile exposed to the frontend."""

    id: str
    label: str
    description: str | None = None
    kind: str = "remote"
    enabled: bool = True

