# backend-python/api/schemas/training.py
from __future__ import annotations

from pydantic import BaseModel


class TrainingSourceStats(BaseModel):
    volumes: int | None = None
    images: int | None = None
    annotations: list[str] = []


class TrainingSourcePublic(BaseModel):
    id: str
    label: str
    type: str
    path: str | None = None
    available: bool = True
    description: str | None = None
    stats: TrainingSourceStats | None = None


class PrepareDatasetRequest(BaseModel):
    dataset_id: str | None = None
    sources: list[str]
    targets: list[str] = ["text"]
    val_split: float = 0.15
    test_split: float = 0.0
    link_mode: str = "copy"
    seed: int = 1337
    overwrite: bool = False


class PrepareDatasetStats(BaseModel):
    train_images: int
    val_images: int
    test_images: int
    train_labels: int
    val_labels: int
    test_labels: int


class PrepareDatasetResponse(BaseModel):
    dataset_id: str
    path: str
    stats: PrepareDatasetStats


class PreparedDatasetStats(BaseModel):
    train_images: int
    val_images: int
    test_images: int
    train_labels: int
    val_labels: int
    test_labels: int


class PreparedDatasetPublic(BaseModel):
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
    ultralytics_version: str
    families: list[str]
