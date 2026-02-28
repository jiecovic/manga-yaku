# backend-python/api/schemas/training.py
"""Schemas for training source discovery and dataset/training payloads."""

from __future__ import annotations

from pydantic import BaseModel


class TrainingSourceStats(BaseModel):
    """Optional summary stats discovered for a training source."""

    volumes: int | None = None
    images: int | None = None
    annotations: list[str] = []


class TrainingSourcePublic(BaseModel):
    """One training source exposed by the catalog endpoint."""

    id: str
    label: str
    type: str
    path: str | None = None
    available: bool = True
    description: str | None = None
    stats: TrainingSourceStats | None = None


class PrepareDatasetRequest(BaseModel):
    """Payload for preparing a train/val/test dataset split."""

    dataset_id: str | None = None
    sources: list[str]
    targets: list[str] = ["text"]
    val_split: float = 0.15
    test_split: float = 0.0
    link_mode: str = "copy"
    seed: int = 1337
    overwrite: bool = False


class PrepareDatasetStats(BaseModel):
    """Counts produced by one dataset preparation run."""

    train_images: int
    val_images: int
    test_images: int
    train_labels: int
    val_labels: int
    test_labels: int


class PrepareDatasetResponse(BaseModel):
    """Response for successful dataset preparation."""

    dataset_id: str
    path: str
    stats: PrepareDatasetStats


class PreparedDatasetStats(BaseModel):
    """Persisted counts for an existing prepared dataset."""

    train_images: int
    val_images: int
    test_images: int
    train_labels: int
    val_labels: int
    test_labels: int


class PreparedDatasetPublic(BaseModel):
    """Metadata record for one prepared dataset artifact."""

    id: str
    path: str
    created_at: str | None = None
    targets: list[str] = []
    val_split: float | None = None
    test_split: float | None = None
    image_mode: str | None = None
    seed: int | None = None
    stats: PreparedDatasetStats | None = None


class TrainingModelsResponse(BaseModel):
    """Available model families/options from the training backend."""

    ultralytics_version: str
    families: list[str]
