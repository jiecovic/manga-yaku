# backend-python/api/schemas/jobs.py
from __future__ import annotations

from pydantic import BaseModel


class CreateOcrBoxJobRequest(BaseModel):
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
    profileId: str
    profileIds: list[str] | None = None
    volumeId: str
    filename: str
    skipExisting: bool = True


class CreateTranslateBoxJobRequest(BaseModel):
    profileId: str
    volumeId: str
    filename: str
    boxId: int
    usePageContext: bool = False
    boxOrder: int | None = None


class CreateTranslatePageJobRequest(BaseModel):
    profileId: str
    volumeId: str
    filename: str
    usePageContext: bool = False
    skipExisting: bool = True


class CreateAgentTranslatePageJobRequest(BaseModel):
    volumeId: str
    filename: str
    detectionProfileId: str | None = None
    ocrProfiles: list[str] | None = None
    sourceLanguage: str | None = None
    targetLanguage: str | None = None
    modelId: str | None = None


class CreateBoxDetectionJobRequest(BaseModel):
    volumeId: str
    filename: str
    profileId: str | None = None
    task: str | None = None
    replaceExisting: bool = True


class CreatePrepareDatasetJobRequest(BaseModel):
    dataset_id: str | None = None
    sources: list[str]
    targets: list[str] = ["text"]
    val_split: float = 0.15
    test_split: float = 0.0
    link_mode: str = "copy"
    seed: int = 1337
    overwrite: bool = False


class CreateTrainModelJobRequest(BaseModel):
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
    jobId: str
