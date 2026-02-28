# backend-python/api/schemas/jobs.py
"""Schemas for job creation endpoints and job capability metadata.

Field names intentionally follow the public API contract used by the frontend
(mostly camelCase for legacy compatibility).
"""

from __future__ import annotations

from pydantic import BaseModel


class CreateOcrBoxJobRequest(BaseModel):
    """Create one OCR task for a single box crop."""

    profileId: str
    volumeId: str
    filename: str
    x: float
    y: float
    width: float
    height: float
    boxId: int | None = None
    boxOrder: int | None = None


class CreateOcrPageJobRequest(BaseModel):
    """Create a workflow that OCRs all boxes on a page."""

    profileId: str
    profileIds: list[str] | None = None
    volumeId: str
    filename: str
    skipExisting: bool = True


class CreateTranslateBoxJobRequest(BaseModel):
    """Create one single-box translation task."""

    profileId: str
    volumeId: str
    filename: str
    boxId: int
    usePageContext: bool | None = None
    boxOrder: int | None = None


class CreateTranslatePageJobRequest(BaseModel):
    """Legacy full-page translate job request shape."""

    profileId: str
    volumeId: str
    filename: str
    usePageContext: bool = False
    skipExisting: bool = True


class CreateAgentTranslatePageJobRequest(BaseModel):
    """Create the staged agent translate-page workflow job."""

    volumeId: str
    filename: str
    detectionProfileId: str | None = None
    ocrProfiles: list[str] | None = None
    sourceLanguage: str | None = None
    targetLanguage: str | None = None
    modelId: str | None = None
    forceRerun: bool = False


class CreateBoxDetectionJobRequest(BaseModel):
    """Create a page-level text-box detection task."""

    volumeId: str
    filename: str
    profileId: str | None = None
    task: str | None = None
    replaceExisting: bool = True


class CreatePrepareDatasetJobRequest(BaseModel):
    """Create a dataset preparation job for training inputs."""

    dataset_id: str | None = None
    sources: list[str]
    targets: list[str] = ["text"]
    val_split: float = 0.15
    test_split: float = 0.0
    link_mode: str = "copy"
    seed: int = 1337
    overwrite: bool = False


class CreateTrainModelJobRequest(BaseModel):
    """Create a model training job for a prepared dataset."""

    dataset_id: str
    model_family: str = "yolo26"
    model_size: str = "n"
    pretrained: bool = True
    epochs: int = 50
    batch_size: int = 8
    workers: int = 0
    image_size: int = 1024
    device: str = "auto"
    patience: int = 20
    augmentations: bool = True
    dry_run: bool = False


class CreateJobResponse(BaseModel):
    """Job creation response containing the new job identifier."""

    jobId: str


class JobCapability(BaseModel):
    """Feature flag entry describing whether a job type is available."""

    enabled: bool
    reason: str | None = None


class JobsCapabilitiesResponse(BaseModel):
    """Capabilities payload for all frontend-visible job actions."""

    ocr_page: JobCapability
    ocr_box: JobCapability
    translate_page: JobCapability
    translate_box: JobCapability
    agent_translate_page: JobCapability
