# backend-python/api/schemas/settings.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SettingsResponse(BaseModel):
    scope: str
    values: dict[str, Any]
    defaults: dict[str, Any]
    options: dict[str, Any]


class UpdateSettingsRequest(BaseModel):
    scope: str = "global"
    values: dict[str, Any]


class AgentTranslateSettings(BaseModel):
    model_id: str
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class AgentTranslateSettingsResponse(BaseModel):
    value: AgentTranslateSettings
    defaults: AgentTranslateSettings
    options: dict[str, Any]


class UpdateAgentTranslateSettingsRequest(BaseModel):
    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class OcrProfileSettingsItem(BaseModel):
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
    profiles: list[OcrProfileSettingsItem]
    options: dict[str, Any]


class UpdateOcrProfileSettingsItem(BaseModel):
    profile_id: str
    agent_enabled: bool | None = None
    model_id: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None


class UpdateOcrProfileSettingsRequest(BaseModel):
    profiles: list[UpdateOcrProfileSettingsItem]
