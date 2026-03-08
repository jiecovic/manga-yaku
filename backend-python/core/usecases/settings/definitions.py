# backend-python/core/usecases/settings/definitions.py
"""Setting key definitions, metadata, and validation constraints."""

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
    "detection.containment_threshold": SettingSpec(
        default=None,
        value_type=(float, int, type(None)),
        min_value=0.0,
        max_value=1.0,
    ),
    "page_translation.detection_profile_id": SettingSpec(
        default="",
        value_type=str,
    ),
    "translation.single_box.use_context": SettingSpec(
        default=True,
        value_type=bool,
    ),
    "page_translation.include_prior_context_summary": SettingSpec(
        default=True,
        value_type=bool,
    ),
    "page_translation.include_prior_characters": SettingSpec(
        default=True,
        value_type=bool,
    ),
    "page_translation.include_prior_open_threads": SettingSpec(
        default=True,
        value_type=bool,
    ),
    "page_translation.include_prior_glossary": SettingSpec(
        default=True,
        value_type=bool,
    ),
    "page_translation.merge.max_output_tokens": SettingSpec(
        default=768,
        value_type=int,
        min_value=128,
        max_value=4096,
    ),
    "page_translation.merge.reasoning_effort": SettingSpec(
        default="low",
        value_type=str,
        choices=("low", "medium", "high"),
    ),
    "agent.chat.max_turns": SettingSpec(
        default=18,
        value_type=int,
        min_value=1,
        max_value=200,
    ),
    "agent.chat.max_output_tokens": SettingSpec(
        default=2048,
        value_type=int,
        min_value=128,
        max_value=64000,
    ),
    "ocr.parallelism.local": SettingSpec(
        default=4,
        value_type=int,
        min_value=1,
        max_value=32,
    ),
    "ocr.parallelism.remote": SettingSpec(
        default=2,
        value_type=int,
        min_value=1,
        max_value=32,
    ),
    "ocr.parallelism.max_workers": SettingSpec(
        default=6,
        value_type=int,
        min_value=1,
        max_value=64,
    ),
    "ocr.parallelism.lease_seconds": SettingSpec(
        default=180,
        value_type=int,
        min_value=30,
        max_value=3600,
    ),
    "ocr.parallelism.task_timeout_seconds": SettingSpec(
        default=180,
        value_type=int,
        min_value=15,
        max_value=3600,
    ),
}


DEFAULT_SETTINGS: dict[str, Any] = {key: spec.default for key, spec in SETTING_SPECS.items()}
