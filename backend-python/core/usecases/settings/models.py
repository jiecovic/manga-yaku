# backend-python/core/usecases/settings/models.py
"""Typed setting models used by the settings service layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from infra.llm.model_capabilities import model_applies_reasoning_effort, model_applies_temperature


@dataclass(frozen=True)
class DetectionSettings:
    conf_threshold: float | None
    iou_threshold: float | None
    containment_threshold: float | None
    page_translation_detection_profile_id: str


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


@dataclass(frozen=True)
class ModelRuntimeSettings:
    """Stable internal shape for model/runtime tuning settings."""

    model_id: str | None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None

    @classmethod
    def empty(cls) -> ModelRuntimeSettings:
        return cls(
            model_id=None,
            max_output_tokens=None,
            reasoning_effort=None,
            temperature=None,
        )

    def to_payload(self) -> dict[str, Any]:
        return dict(asdict(self))

    def apply_to_config(
        self,
        base_cfg: dict[str, Any],
        *,
        token_key: str | None = None,
    ) -> dict[str, Any]:
        """Apply the normalized runtime settings to a provider config dict."""
        cfg = dict(base_cfg)
        resolved_model_id = self.model_id
        if resolved_model_id:
            cfg["model"] = resolved_model_id
        resolved_model = cfg.get("model")
        if self.max_output_tokens is not None:
            resolved_token_key = token_key
            if resolved_token_key is None:
                if "max_output_tokens" in cfg:
                    resolved_token_key = "max_output_tokens"
                elif "max_completion_tokens" in cfg:
                    resolved_token_key = "max_completion_tokens"
                else:
                    resolved_token_key = "max_tokens"
            cfg[resolved_token_key] = self.max_output_tokens
        if model_applies_temperature(resolved_model):
            if self.temperature is not None:
                cfg["temperature"] = self.temperature
        else:
            cfg.pop("temperature", None)
        if model_applies_reasoning_effort(resolved_model):
            if self.reasoning_effort:
                cfg["reasoning"] = {"effort": self.reasoning_effort}
        else:
            cfg.pop("reasoning", None)
        return cfg


@dataclass(frozen=True)
class PageTranslationRuntimeSettings(ModelRuntimeSettings):
    """Resolved page-translation runtime settings."""


@dataclass(frozen=True)
class OcrProfileRuntimeSettings(ModelRuntimeSettings):
    """Resolved OCR profile runtime settings."""

    page_translation_enabled: bool = True

    @classmethod
    def from_model_settings(
        cls,
        settings: ModelRuntimeSettings,
        *,
        page_translation_enabled: bool = True,
    ) -> OcrProfileRuntimeSettings:
        return cls(
            model_id=settings.model_id,
            max_output_tokens=settings.max_output_tokens,
            reasoning_effort=settings.reasoning_effort,
            temperature=settings.temperature,
            page_translation_enabled=page_translation_enabled,
        )

    def model_settings(self) -> ModelRuntimeSettings:
        return ModelRuntimeSettings(
            model_id=self.model_id,
            max_output_tokens=self.max_output_tokens,
            reasoning_effort=self.reasoning_effort,
            temperature=self.temperature,
        )


@dataclass(frozen=True)
class TranslationProfileRuntimeSettings(ModelRuntimeSettings):
    """Resolved translation profile runtime settings."""

    single_box_enabled: bool = True

    @classmethod
    def from_model_settings(
        cls,
        settings: ModelRuntimeSettings,
        *,
        single_box_enabled: bool = True,
    ) -> TranslationProfileRuntimeSettings:
        return cls(
            model_id=settings.model_id,
            max_output_tokens=settings.max_output_tokens,
            reasoning_effort=settings.reasoning_effort,
            temperature=settings.temperature,
            single_box_enabled=single_box_enabled,
        )

    def model_settings(self) -> ModelRuntimeSettings:
        return ModelRuntimeSettings(
            model_id=self.model_id,
            max_output_tokens=self.max_output_tokens,
            reasoning_effort=self.reasoning_effort,
            temperature=self.temperature,
        )


@dataclass(frozen=True)
class OcrProfileSettingsView:
    """API-facing OCR profile settings projection built from typed core data."""

    id: str
    label: str
    description: str
    kind: str
    enabled: bool
    page_translation_enabled: bool
    model_id: str | None
    max_output_tokens: int | None
    reasoning_effort: str | None
    temperature: float | None

    def to_payload(self) -> dict[str, Any]:
        return dict(asdict(self))


@dataclass(frozen=True)
class TranslationProfileSettingsView:
    """API-facing translation profile settings projection built from typed core data."""

    id: str
    label: str
    description: str
    kind: str
    enabled: bool
    single_box_enabled: bool
    effective_enabled: bool
    model_id: str | None
    max_output_tokens: int | None
    reasoning_effort: str | None
    temperature: float | None

    def to_payload(self) -> dict[str, Any]:
        return dict(asdict(self))
