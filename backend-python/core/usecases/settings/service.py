# backend-python/core/usecases/settings/service.py
"""Service API for reading/updating settings settings."""

from __future__ import annotations

from typing import Any

from infra.db.settings_store import list_settings, upsert_settings

from .definitions import DEFAULT_SETTINGS, SETTING_SPECS, SettingSpec
from .models import DetectionSettings, OcrLabelOverrides, OcrParallelismSettings


def _coerce_value(key: str, value: Any, spec: SettingSpec) -> Any:
    if isinstance(value, list) and spec.value_type is list:
        return [str(item) for item in value]

    if spec.value_type is dict:
        if not isinstance(value, dict):
            raise ValueError(f"{key} must be an object")
        return {str(k): v for k, v in value.items()}

    if spec.value_type is int:
        if isinstance(value, list):
            raise ValueError(f"{key} must be an integer")
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer") from None

    if spec.value_type is str:
        if value is None:
            raise ValueError(f"{key} must be a string")
        return str(value)

    if isinstance(spec.value_type, tuple) and type(None) in spec.value_type:
        if value is None or value == "":
            return None
        if isinstance(value, list):
            raise ValueError(f"{key} must be a number or null")
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number or null") from None

    if isinstance(value, spec.value_type):
        return value

    raise ValueError(f"{key} has invalid type")


def _validate_value(key: str, value: Any, spec: SettingSpec) -> Any:
    coerced = _coerce_value(key, value, spec)

    if spec.choices and coerced is not None:
        if str(coerced) not in spec.choices:
            raise ValueError(f"{key} must be one of {spec.choices}")

    if isinstance(coerced, int | float):
        if spec.min_value is not None and coerced < spec.min_value:
            raise ValueError(f"{key} must be >= {spec.min_value}")
        if spec.max_value is not None and coerced > spec.max_value:
            raise ValueError(f"{key} must be <= {spec.max_value}")

    if isinstance(coerced, list) and spec.choices:
        for item in coerced:
            if str(item) not in spec.choices:
                raise ValueError(f"{key} must contain only {spec.choices}")

    return coerced


def resolve_settings(scope: str = "global") -> dict[str, Any]:
    values = dict(DEFAULT_SETTINGS)
    stored = list_settings(scope)
    values.update(stored)
    return values


def get_setting_value(key: str, *, scope: str = "global") -> Any:
    values = resolve_settings(scope)
    return values.get(key)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(
    value: Any,
    *,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


def resolve_detection_settings(scope: str = "global") -> DetectionSettings:
    values = resolve_settings(scope)
    conf = _coerce_optional_float(values.get("detection.conf_threshold"))
    iou = _coerce_optional_float(values.get("detection.iou_threshold"))
    containment = _coerce_optional_float(values.get("detection.containment_threshold"))
    if conf is not None:
        conf = min(max(conf, 0.0), 1.0)
    if iou is not None:
        iou = min(max(iou, 0.0), 1.0)
    if containment is not None:
        containment = min(max(containment, 0.0), 1.0)
    raw_profile_id = values.get("page_translation.detection_profile_id")
    profile_id = str(raw_profile_id).strip() if raw_profile_id is not None else ""
    return DetectionSettings(
        conf_threshold=conf,
        iou_threshold=iou,
        containment_threshold=containment,
        page_translation_detection_profile_id=profile_id,
    )


def resolve_ocr_parallelism_settings(scope: str = "global") -> OcrParallelismSettings:
    values = resolve_settings(scope)
    local = _coerce_int(
        values.get("ocr.parallelism.local"),
        default=4,
        min_value=1,
        max_value=32,
    )
    remote = _coerce_int(
        values.get("ocr.parallelism.remote"),
        default=2,
        min_value=1,
        max_value=32,
    )
    max_workers = _coerce_int(
        values.get("ocr.parallelism.max_workers"),
        default=6,
        min_value=1,
        max_value=64,
    )
    lease_seconds = _coerce_int(
        values.get("ocr.parallelism.lease_seconds"),
        default=180,
        min_value=30,
        max_value=3600,
    )
    task_timeout_seconds = _coerce_int(
        values.get("ocr.parallelism.task_timeout_seconds"),
        default=180,
        min_value=15,
        max_value=3600,
    )
    return OcrParallelismSettings(
        local=local,
        remote=remote,
        max_workers=max_workers,
        lease_seconds=lease_seconds,
        task_timeout_seconds=task_timeout_seconds,
    )


def resolve_ocr_label_overrides(scope: str = "global") -> OcrLabelOverrides:
    values = resolve_settings(scope)
    raw = values.get("ocr.label_overrides")
    if not isinstance(raw, dict):
        return OcrLabelOverrides(values={})
    out: dict[str, str] = {}
    for key, value in raw.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        out[normalized_key] = str(value)
    return OcrLabelOverrides(values=out)


def update_settings(scope: str, values: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(values, dict):
        raise ValueError("values must be an object")

    updates: dict[str, Any] = {}
    for key, raw_value in values.items():
        spec = SETTING_SPECS.get(key)
        if spec is None:
            raise ValueError(f"Unknown setting: {key}")
        updates[key] = _validate_value(key, raw_value, spec)

    if not updates:
        return resolve_settings(scope)

    upsert_settings(scope, updates)
    return resolve_settings(scope)
