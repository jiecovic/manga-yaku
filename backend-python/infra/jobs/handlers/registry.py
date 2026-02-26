# backend-python/infra/jobs/handlers/registry.py
from __future__ import annotations

from .agent import AgentTranslatePageJobHandler
from .detection import BoxDetectionJobHandler
from .training import PrepareDatasetJobHandler, TrainModelJobHandler

HANDLERS = {
    "box_detection": BoxDetectionJobHandler(),
    "agent_translate_page": AgentTranslatePageJobHandler(),
    "prepare_dataset": PrepareDatasetJobHandler(),
    "train_model": TrainModelJobHandler(),
}
