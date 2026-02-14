# backend-python/api/routers/settings.py
from __future__ import annotations

from typing import Any

from api.schemas.settings import (
    AgentTranslateSettingsResponse,
    OcrProfileSettingsResponse,
    SettingsResponse,
    UpdateAgentTranslateSettingsRequest,
    UpdateOcrProfileSettingsRequest,
    UpdateSettingsRequest,
)
from config import AGENT_MODELS
from core.usecases.agent.settings import (
    agent_translate_defaults,
    resolve_agent_translate_settings,
    update_agent_translate_settings,
)
from core.usecases.ocr.profile_settings import (
    list_ocr_profiles_with_settings,
    update_ocr_profile_settings,
)
from core.usecases.settings.definitions import DEFAULT_SETTINGS
from core.usecases.settings.service import resolve_settings, update_settings
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["settings"])


def _build_options() -> dict[str, Any]:
    return {
        "detection.conf_threshold": {"min": 0.0, "max": 1.0},
        "detection.iou_threshold": {"min": 0.0, "max": 1.0},
    }


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(scope: str = "global") -> SettingsResponse:
    values = resolve_settings(scope)
    return SettingsResponse(
        scope=scope,
        values=values,
        defaults=DEFAULT_SETTINGS,
        options=_build_options(),
    )


@router.put("/settings", response_model=SettingsResponse)
async def put_settings(req: UpdateSettingsRequest) -> SettingsResponse:
    try:
        values = update_settings(req.scope, dict(req.values))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SettingsResponse(
        scope=req.scope,
        values=values,
        defaults=DEFAULT_SETTINGS,
        options=_build_options(),
    )


@router.get(
    "/settings/agent-translate",
    response_model=AgentTranslateSettingsResponse,
)
async def get_agent_translate_settings() -> AgentTranslateSettingsResponse:
    value = resolve_agent_translate_settings()
    defaults = agent_translate_defaults()
    return AgentTranslateSettingsResponse(
        value=value,
        defaults=defaults,
        options={
            "models": AGENT_MODELS,
            "reasoning_effort": ["low", "medium", "high"],
        },
    )


@router.put(
    "/settings/agent-translate",
    response_model=AgentTranslateSettingsResponse,
)
async def put_agent_translate_settings(
    req: UpdateAgentTranslateSettingsRequest,
) -> AgentTranslateSettingsResponse:
    try:
        value = update_agent_translate_settings(req.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AgentTranslateSettingsResponse(
        value=value,
        defaults=agent_translate_defaults(),
        options={
            "models": AGENT_MODELS,
            "reasoning_effort": ["low", "medium", "high"],
        },
    )


@router.get(
    "/settings/ocr-profiles",
    response_model=OcrProfileSettingsResponse,
)
async def get_ocr_profile_settings() -> OcrProfileSettingsResponse:
    profiles = list_ocr_profiles_with_settings()
    models = set(AGENT_MODELS)
    for profile in profiles:
        model_id = profile.get("model_id")
        if model_id:
            models.add(str(model_id))
    return OcrProfileSettingsResponse(
        profiles=profiles,
        options={
            "models": sorted(models),
            "reasoning_effort": ["low", "medium", "high"],
        },
    )


@router.put(
    "/settings/ocr-profiles",
    response_model=OcrProfileSettingsResponse,
)
async def put_ocr_profile_settings(
    req: UpdateOcrProfileSettingsRequest,
) -> OcrProfileSettingsResponse:
    try:
        profiles = update_ocr_profile_settings(
            [item.model_dump(exclude_unset=True) for item in req.profiles]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    models = set(AGENT_MODELS)
    for profile in profiles:
        model_id = profile.get("model_id")
        if model_id:
            models.add(str(model_id))
    return OcrProfileSettingsResponse(
        profiles=profiles,
        options={
            "models": sorted(models),
            "reasoning_effort": ["low", "medium", "high"],
        },
    )
