# backend-python/core/usecases/settings/definitions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingSpec:
    default: Any
    value_type: type | tuple[type, ...]
    choices: tuple[str, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None


SETTING_SPECS: dict[str, SettingSpec] = {
    "ocr.label_overrides": SettingSpec(
        default={},
        value_type=dict,
    ),
    "detection.conf_threshold": SettingSpec(
        default=None,
        value_type=(float, int, type(None)),
        min_value=0.0,
        max_value=1.0,
    ),
    "detection.iou_threshold": SettingSpec(
        default=None,
        value_type=(float, int, type(None)),
        min_value=0.0,
        max_value=1.0,
    ),
    "agent.translate.detection_profile_id": SettingSpec(
        default="",
        value_type=str,
    ),
}


DEFAULT_SETTINGS: dict[str, Any] = {
    key: spec.default for key, spec in SETTING_SPECS.items()
}
