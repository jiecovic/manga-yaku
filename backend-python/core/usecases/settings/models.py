from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionSettings:
    conf_threshold: float | None
    iou_threshold: float | None
    containment_threshold: float | None
    agent_detection_profile_id: str


@dataclass(frozen=True)
class OcrParallelismSettings:
    local: int
    remote: int
    max_workers: int
    lease_seconds: int
    task_timeout_seconds: int

    @property
    def requested_workers(self) -> int:
        return max(1, self.local + self.remote)


@dataclass(frozen=True)
class OcrLabelOverrides:
    values: dict[str, str]
