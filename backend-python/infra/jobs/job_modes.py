# backend-python/infra/jobs/job_modes.py
"""Canonical job mode boundaries for persisted and hybrid workflows."""

from __future__ import annotations

from typing import Final

# Workflow/job type ids.
AGENT_WORKFLOW_TYPE: Final[str] = "agent_translate_page"
OCR_PAGE_WORKFLOW_TYPE: Final[str] = "ocr_page"
OCR_BOX_WORKFLOW_TYPE: Final[str] = "ocr_box"
TRANSLATE_BOX_WORKFLOW_TYPE: Final[str] = "translate_box"
BOX_DETECTION_JOB_TYPE: Final[str] = "box_detection"
PREPARE_DATASET_JOB_TYPE: Final[str] = "prepare_dataset"
TRAIN_MODEL_JOB_TYPE: Final[str] = "train_model"

# DB-task workflows: persisted workflow + persisted task fanout workers.
DB_TASK_WORKFLOW_TYPES: Final[frozenset[str]] = frozenset(
    {
        OCR_PAGE_WORKFLOW_TYPE,
        OCR_BOX_WORKFLOW_TYPE,
        TRANSLATE_BOX_WORKFLOW_TYPE,
    }
)

# Persisted utility workflows: single workflow/task pair executed by the DB utility worker.
UTILITY_WORKFLOW_TYPES: Final[tuple[str, ...]] = (
    BOX_DETECTION_JOB_TYPE,
    PREPARE_DATASET_JOB_TYPE,
    TRAIN_MODEL_JOB_TYPE,
)

# Hybrid workflows: memory queue entrypoint, but workflow state persisted in DB.
HYBRID_WORKFLOW_TYPES: Final[frozenset[str]] = frozenset(
    {
        AGENT_WORKFLOW_TYPE,
    }
)

# Any workflow with persisted state in workflow/task tables.
PERSISTED_WORKFLOW_TYPES: Final[frozenset[str]] = frozenset(
    DB_TASK_WORKFLOW_TYPES | HYBRID_WORKFLOW_TYPES | frozenset(UTILITY_WORKFLOW_TYPES)
)
