# backend-python/infra/jobs/handlers/registry.py
from __future__ import annotations

from .agent import AgentTranslatePageJobHandler
from .detection import BoxDetectionJobHandler
from .ocr import OcrBoxJobHandler, OcrPageJobHandler
from .training import PrepareDatasetJobHandler, TrainModelJobHandler
from .translation import TranslateBoxJobHandler, TranslatePageJobHandler

HANDLERS = {
    "ocr_box": OcrBoxJobHandler(),
    "translate_box": TranslateBoxJobHandler(),
    "ocr_page": OcrPageJobHandler(),
    "translate_page": TranslatePageJobHandler(),
    "box_detection": BoxDetectionJobHandler(),
    "agent_translate_page": AgentTranslatePageJobHandler(),
    "prepare_dataset": PrepareDatasetJobHandler(),
    "train_model": TrainModelJobHandler(),
}
