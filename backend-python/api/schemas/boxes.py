# backend-python/api/schemas/boxes.py
"""Schemas for page box CRUD and text patch endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class Box(BaseModel):
    """Editable page box record returned by box endpoints."""

    id: int
    orderIndex: int | None = None
    x: float
    y: float
    width: float
    height: float
    type: str = "text"
    source: str | None = None
    runId: str | None = None
    modelId: str | None = None
    modelLabel: str | None = None
    modelVersion: str | None = None
    modelPath: str | None = None
    modelHash: str | None = None
    modelTask: str | None = None
    text: str | None = ""
    translation: str | None = ""


class BoxPage(BaseModel):
    """Page payload containing boxes and optional page-level context text."""

    boxes: list[Box]
    # None = field omitted -> keep existing context on save
    # ""   = explicitly clear context
    pageContext: str | None = None


class BoxTextPatch(BaseModel):
    """Partial text/translation update for a single box."""

    text: str | None = None
    translation: str | None = None

