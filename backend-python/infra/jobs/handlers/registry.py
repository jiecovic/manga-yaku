# backend-python/infra/jobs/handlers/registry.py
"""Job handler implementation for registry tasks."""

from __future__ import annotations

from infra.jobs.job_modes import (
    AGENT_WORKFLOW_TYPE,
    BOX_DETECTION_JOB_TYPE,
    PREPARE_DATASET_JOB_TYPE,
    TRAIN_MODEL_JOB_TYPE,
)

from .agent import AgentTranslatePageJobHandler
from .detection import BoxDetectionJobHandler
from .training import PrepareDatasetJobHandler, TrainModelJobHandler

HANDLERS = {
    BOX_DETECTION_JOB_TYPE: BoxDetectionJobHandler(),
    AGENT_WORKFLOW_TYPE: AgentTranslatePageJobHandler(),
    PREPARE_DATASET_JOB_TYPE: PrepareDatasetJobHandler(),
    TRAIN_MODEL_JOB_TYPE: TrainModelJobHandler(),
}
