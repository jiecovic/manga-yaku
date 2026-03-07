# backend-python/infra/jobs/handlers/registry.py
"""Job handler implementation for registry tasks."""

from __future__ import annotations

from infra.jobs.job_modes import (
    BOX_DETECTION_JOB_TYPE,
    PAGE_TRANSLATION_WORKFLOW_TYPE,
    PREPARE_DATASET_JOB_TYPE,
    TRAIN_MODEL_JOB_TYPE,
)

from .detection import BoxDetectionJobHandler
from .page_translation import PageTranslationJobHandler
from .training import PrepareDatasetJobHandler, TrainModelJobHandler

HANDLERS = {
    BOX_DETECTION_JOB_TYPE: BoxDetectionJobHandler(),
    PAGE_TRANSLATION_WORKFLOW_TYPE: PageTranslationJobHandler(),
    PREPARE_DATASET_JOB_TYPE: PrepareDatasetJobHandler(),
    TRAIN_MODEL_JOB_TYPE: TrainModelJobHandler(),
}
