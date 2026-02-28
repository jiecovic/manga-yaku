# backend-python/api/schemas/settings.py
"""Schemas for global settings and profile-level runtime overrides."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    """Resolved settings payload (current values + defaults + options)."""

    scope: str
    values: dict[str, Any]
    defaults: dict[str, Any]
    options: dict[str, Any]


class UpdateSettingsRequest(BaseModel):
    """Patch request for generic key/value settings scope."""

    scope: str = "global"
    values: dict[str, Any]


class AgentTranslateSettings(BaseModel):
    """Persisted runtime knobs for the agent translate-page LLM."""

    model_id: str
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class AgentTranslateSettingsResponse(BaseModel):
    """Response envelope for agent translate-page settings."""

    value: AgentTranslateSettings
    defaults: AgentTranslateSettings
    options: dict[str, Any]


class UpdateAgentTranslateSettingsRequest(BaseModel):
    """Partial update payload for agent translate-page settings."""

    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class OcrProfileSettingsItem(BaseModel):
    """Resolved OCR profile entry shown in settings UI."""

    id: str
    label: str
    description: str | None = None
    kind: str
    enabled: bool
    agent_enabled: bool
    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class OcrProfileSettingsResponse(BaseModel):
    """Response envelope for OCR profile settings list."""

    profiles: list[OcrProfileSettingsItem]
    options: dict[str, Any]


class UpdateOcrProfileSettingsItem(BaseModel):
    """Per-profile OCR override patch entry."""

    profile_id: str
    agent_enabled: bool | None = None
    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class UpdateOcrProfileSettingsRequest(BaseModel):
    """Batch update payload for OCR profile overrides."""

    profiles: list[UpdateOcrProfileSettingsItem]


class TranslationProfileSettingsItem(BaseModel):
    """Resolved translation profile entry shown in settings UI."""

    id: str
    label: str
    description: str | None = None
    kind: str
    enabled: bool
    single_box_enabled: bool
    effective_enabled: bool
    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class TranslationProfileSettingsResponse(BaseModel):
    """Response envelope for translation profile settings list."""

    profiles: list[TranslationProfileSettingsItem]
    options: dict[str, Any]


class UpdateTranslationProfileSettingsItem(BaseModel):
    """Per-profile translation override patch entry."""

    profile_id: str
    single_box_enabled: bool | None = None
    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class UpdateTranslationProfileSettingsRequest(BaseModel):
    """Batch update payload for translation profile overrides."""

    profiles: list[UpdateTranslationProfileSettingsItem]
