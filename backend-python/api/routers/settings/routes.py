# backend-python/api/routers/settings/routes.py
"""HTTP routes for settings endpoints."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas.settings import (
    AgentTranslateSettingsResponse,
    OcrProfileSettingsResponse,
    SettingsResponse,
    TranslationProfileSettingsResponse,
    UpdateAgentTranslateSettingsRequest,
    UpdateOcrProfileSettingsRequest,
    UpdateSettingsRequest,
    UpdateTranslationProfileSettingsRequest,
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
from core.usecases.translation.profile_settings import (
    list_translation_profiles_with_settings,
    update_translation_profile_settings,
)
from infra.logging.correlation import append_correlation

router = APIRouter(tags=["settings"])
logger = logging.getLogger(__name__)


def _build_options() -> dict[str, Any]:
    return {
        "detection.conf_threshold": {"min": 0.0, "max": 1.0},
        "detection.iou_threshold": {"min": 0.0, "max": 1.0},
        "detection.containment_threshold": {"min": 0.0, "max": 1.0},
        "translation.single_box.use_context": {"type": "boolean"},
        "agent.translate.include_prior_context_summary": {"type": "boolean"},
        "agent.translate.include_prior_characters": {"type": "boolean"},
        "agent.translate.include_prior_open_threads": {"type": "boolean"},
        "agent.translate.include_prior_glossary": {"type": "boolean"},
        "agent.translate.merge.max_output_tokens": {"min": 128, "max": 4096},
        "agent.translate.merge.reasoning_effort": {
            "choices": ["low", "medium", "high"]
        },
        "agent.chat.max_turns": {"min": 1, "max": 200},
        "ocr.parallelism.local": {"min": 1, "max": 32},
        "ocr.parallelism.remote": {"min": 1, "max": 32},
        "ocr.parallelism.max_workers": {"min": 1, "max": 64},
        "ocr.parallelism.lease_seconds": {"min": 30, "max": 3600},
        "ocr.parallelism.task_timeout_seconds": {"min": 15, "max": 3600},
    }


def _is_restart_enabled() -> bool:
    raw = os.environ.get("MANGAYAKU_SELF_RESTART_ENABLED", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _restart_exit_code() -> int:
    raw = os.environ.get("MANGAYAKU_BACKEND_RESTART_EXIT_CODE", "75")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 75
    if value < 0 or value > 255:
        return 75
    return value


def _exit_process_later(delay_seconds: float = 0.25) -> None:
    logger.info(
        append_correlation(
            "Backend restart requested: exiting process",
            {"component": "settings.backend_restart"},
            delay_seconds=f"{max(0.0, delay_seconds):.2f}",
            pid=os.getpid(),
            exit_code=_restart_exit_code(),
        )
    )
    time.sleep(max(0.0, delay_seconds))
    os._exit(_restart_exit_code())


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(scope: str = "global") -> SettingsResponse:
    """Return settings."""
    values = resolve_settings(scope)
    return SettingsResponse(
        scope=scope,
        values=values,
        defaults=DEFAULT_SETTINGS,
        options=_build_options(),
    )


@router.put("/settings", response_model=SettingsResponse)
async def put_settings(req: UpdateSettingsRequest) -> SettingsResponse:
    """Update settings."""
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


@router.post("/settings/backend/restart")
async def restart_backend(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Handle restart backend."""
    enabled = _is_restart_enabled()
    logger.info(
        append_correlation(
            "Restart endpoint called",
            {"component": "settings.backend_restart"},
            pid=os.getpid(),
            enabled=enabled,
            exit_code=_restart_exit_code(),
        )
    )
    if not enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Backend restart is not enabled in this runtime. "
                "Start backend via `npm run dev:backend` or set "
                "`MANGAYAKU_SELF_RESTART_ENABLED=1`."
            ),
        )
    background_tasks.add_task(_exit_process_later)
    return {"status": "restarting"}


@router.get(
    "/settings/agent-translate",
    response_model=AgentTranslateSettingsResponse,
)
async def get_agent_translate_settings() -> AgentTranslateSettingsResponse:
    """Return agent translate settings."""
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
    """Update agent translate settings."""
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
    """Return ocr profile settings."""
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
    """Update ocr profile settings."""
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


@router.get(
    "/settings/translation-profiles",
    response_model=TranslationProfileSettingsResponse,
)
async def get_translation_profile_settings() -> TranslationProfileSettingsResponse:
    """Return translation profile settings."""
    profiles = list_translation_profiles_with_settings()
    models = set(AGENT_MODELS)
    for profile in profiles:
        model_id = profile.get("model_id")
        if model_id:
            models.add(str(model_id))
    return TranslationProfileSettingsResponse(
        profiles=profiles,
        options={
            "models": sorted(models),
            "reasoning_effort": ["low", "medium", "high"],
        },
    )


@router.put(
    "/settings/translation-profiles",
    response_model=TranslationProfileSettingsResponse,
)
async def put_translation_profile_settings(
    req: UpdateTranslationProfileSettingsRequest,
) -> TranslationProfileSettingsResponse:
    """Update translation profile settings."""
    try:
        profiles = update_translation_profile_settings(
            [item.model_dump(exclude_unset=True) for item in req.profiles]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    models = set(AGENT_MODELS)
    for profile in profiles:
        model_id = profile.get("model_id")
        if model_id:
            models.add(str(model_id))
    return TranslationProfileSettingsResponse(
        profiles=profiles,
        options={
            "models": sorted(models),
            "reasoning_effort": ["low", "medium", "high"],
        },
    )
