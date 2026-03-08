# backend-python/core/workflows/page_translation/orchestration/context.py
"""Workflow context builders for page-translation execution."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..state.types import ProgressCallback

NowFn = Callable[[], float]


@dataclass
class WorkflowRunContext:
    """Mutable per-run counters and timings used across workflow stages.

    The workflow runner keeps one of these objects for the whole page-translation
    run so stage helpers can report progress without each helper re-deriving
    counts, durations, and workflow metadata from scratch.
    """

    workflow_run_id: str
    detection_profile_id: str | None
    on_progress: ProgressCallback | None
    now: NowFn = time.monotonic
    detected_boxes: int = 0
    ocr_tasks_total: int = 0
    ocr_tasks_done: int = 0
    updated_boxes: int = 0
    stage_durations_ms: dict[str, int] = field(default_factory=dict)
    _stage_started_at: dict[str, float] = field(default_factory=dict)
    _run_started_at: float = field(init=False)

    def __post_init__(self) -> None:
        self._run_started_at = self.now()

    def start_stage(self, stage_name: str) -> None:
        """Record the start timestamp for a stage before work begins."""
        self._stage_started_at[stage_name] = self.now()

    def finish_stage(self, stage_name: str) -> None:
        """Store elapsed milliseconds for a stage if it was started."""
        started = self._stage_started_at.get(stage_name)
        if started is None:
            return
        elapsed_ms = int((self.now() - started) * 1000)
        self.stage_durations_ms[stage_name] = max(0, elapsed_ms)

    def total_duration_ms(self) -> int:
        """Return total elapsed runtime for the workflow run."""
        return max(0, int((self.now() - self._run_started_at) * 1000))
