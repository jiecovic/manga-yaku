# backend-python/core/usecases/settings/service.py
from __future__ import annotations

from typing import Any

from infra.db.settings_store import list_settings, upsert_settings

from .definitions import DEFAULT_SETTINGS, SETTING_SPECS, SettingSpec


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
