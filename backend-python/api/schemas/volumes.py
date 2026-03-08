# backend-python/api/schemas/volumes.py
"""Schemas for volume/page library, context, and memory endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class VolumeInfo(BaseModel):
    """Volume list entry used by library views."""

    id: str
    name: str
    pageCount: int
    coverImageUrl: str | None


class PageInfo(BaseModel):
    """Page list entry for one volume page."""

    id: str
    volumeId: str
    filename: str
    relPath: str
    imageUrl: str | None = None
    missing: bool | None = None


class CharacterInfo(BaseModel):
    """Character summary row used in memory/context responses."""

    name: str
    gender: str
    info: str


class GlossaryEntry(BaseModel):
    """Glossary entry used in memory/context responses."""

    term: str
    translation: str
    note: str


class VolumeMemoryResponse(BaseModel):
    """Derived volume-level continuity memory payload."""

    rollingSummary: str
    activeCharacters: list[CharacterInfo]
    openThreads: list[str]
    glossary: list[GlossaryEntry]
    lastPageIndex: float | None = None
    updatedAt: str | None = None


class PageMemoryResponse(BaseModel):
    """Derived page-level memory/context snapshot payload."""

    manualNotes: str
    pageSummary: str
    imageSummary: str
    characters: list[CharacterInfo]
    openThreads: list[str]
    glossary: list[GlossaryEntry]
    createdAt: str | None = None
    updatedAt: str | None = None


class ClearMemoryResponse(BaseModel):
    """Simple success response for memory clear endpoints."""

    cleared: bool


class ClearVolumeDerivedDataDetails(BaseModel):
    """Deletion counters returned by derived-data reset operation."""

    pagesTouched: int
    boxesDeleted: int
    detectionRunsDeleted: int
    pageContextSnapshotsDeleted: int
    pageNotesCleared: int
    volumeContextDeleted: int
    agentSessionsDeleted: int
    workflowRunsDeleted: int
    taskRunsDeleted: int
    taskAttemptEventsDeleted: int
    llmCallLogsDeleted: int
    llmPayloadFilesDeleted: int
    pageTranslationDebugFilesDeleted: int


class ClearVolumeDerivedDataResponse(BaseModel):
    """Top-level response for full per-volume derived-state reset."""

    cleared: bool
    details: ClearVolumeDerivedDataDetails


class CreateVolumeRequest(BaseModel):
    """Payload for creating a new library volume."""

    name: str


class MissingVolume(BaseModel):
    """Volume missing on disk but present in DB during sync checks."""

    id: str
    name: str


class PruneMissingRequest(BaseModel):
    """Request to prune missing volume records from DB."""

    ids: list[str]


class MissingPage(BaseModel):
    """Page missing on disk but present in DB during sync checks."""

    volumeId: str
    filename: str


class PruneMissingPagesRequest(BaseModel):
    """Request to prune missing page records from DB."""

    pages: list[MissingPage]
