# backend-python/infra/jobs/handlers/registry.py
from __future__ import annotations

from .agent import AgentTranslatePageJobHandler
from .detection import BoxDetectionJobHandler
from .training import PrepareDatasetJobHandler, TrainModelJobHandler
from .translation import TranslateBoxJobHandler

HANDLERS = {
    "box_detection": BoxDetectionJobHandler(),
    "translate_box": TranslateBoxJobHandler(),
    "agent_translate_page": AgentTranslatePageJobHandler(),
    "prepare_dataset": PrepareDatasetJobHandler(),
    "train_model": TrainModelJobHandler(),
}
