# backend-python/api/routers/training.py
from __future__ import annotations

from api.schemas.training import (
    PrepareDatasetRequest,
    PrepareDatasetResponse,
    PrepareDatasetStats,
    PreparedDatasetPublic,
    TrainingModelsResponse,
    TrainingSourcePublic,
)
from fastapi import APIRouter, HTTPException
from infra.training.catalog import (
    detect_model_families,
    resolve_training_sources,
)
from infra.training.catalog import (
    list_prepared_datasets as list_prepared_datasets_catalog,
)
from infra.training.catalog import (
    list_training_sources as list_training_sources_catalog,
)
from infra.training.dataset_builder import DatasetBuildError, prepare_dataset

router = APIRouter(tags=["training"])


@router.get("/training/sources", response_model=list[TrainingSourcePublic])
def list_training_sources() -> list[TrainingSourcePublic]:
    return list_training_sources_catalog()


@router.get("/training/models", response_model=TrainingModelsResponse)
def list_training_models() -> TrainingModelsResponse:
    version, families = detect_model_families()
    return TrainingModelsResponse(
        ultralytics_version=version,
        families=families,
    )


@router.get("/training/datasets", response_model=list[PreparedDatasetPublic])
def list_prepared_datasets() -> list[PreparedDatasetPublic]:
    return list_prepared_datasets_catalog()


@router.post("/training/datasets/prepare", response_model=PrepareDatasetResponse)
def prepare_training_dataset(
    payload: PrepareDatasetRequest,
) -> PrepareDatasetResponse:
    if not payload.sources:
        raise HTTPException(status_code=400, detail="No sources selected")
    try:
        source_dirs = resolve_training_sources(
            payload.sources,
            allowed_types={"manga109s"},
        )
    except ValueError as exc:
        message = str(exc)
        if message.startswith("Source not found"):
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    try:
        dataset_id, out_dir, stats = prepare_dataset(
            dataset_id=payload.dataset_id,
            source_dirs=source_dirs,
            targets=payload.targets,
            val_split=payload.val_split,
            test_split=payload.test_split,
            link_mode=payload.link_mode,
            seed=payload.seed,
            overwrite=payload.overwrite,
        )
    except DatasetBuildError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PrepareDatasetResponse(
        dataset_id=dataset_id,
        path=str(out_dir),
        stats=PrepareDatasetStats(
            train_images=stats.train_images,
            val_images=stats.val_images,
            test_images=stats.test_images,
            train_labels=stats.train_labels,
            val_labels=stats.val_labels,
            test_labels=stats.test_labels,
        ),
    )
