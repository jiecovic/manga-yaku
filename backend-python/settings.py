# backend-python/settings.py
"""Runtime settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}


def _parse_bool(raw: str | None, *, name: str, default: bool) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ValueError(f"{name} must be a boolean (got {raw!r})")


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_log_level(raw: str | None) -> str:
    if not raw:
        return "INFO"
    level = raw.strip().upper()
    if level == "WARN":
        level = "WARNING"
    if level not in _LOG_LEVELS:
        raise ValueError(f"LOG_LEVEL must be one of {_LOG_LEVELS} (got {raw!r})")
    return level


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    database_url: str
    debug_prompts: bool
    cors_origins: list[str]
    cors_allow_credentials: bool
    log_level: str
    db_init: bool


def load_settings() -> Settings:
    cors_raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173,http://127.0.0.1:5173",
    )
    cors_origins = _parse_csv(cors_raw)
    cors_allow_credentials = _parse_bool(
        os.getenv("CORS_ALLOW_CREDENTIALS"),
        name="CORS_ALLOW_CREDENTIALS",
        default=False,
    )
    debug_prompts = _parse_bool(
        os.getenv("DEBUG_PROMPTS"),
        name="DEBUG_PROMPTS",
        default=False,
    )
    db_init = _parse_bool(
        os.getenv("DB_INIT"),
        name="DB_INIT",
        default=True,
    )

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://mangayaku:mangayaku@localhost:5433/mangayaku",
        ),
        debug_prompts=debug_prompts,
        cors_origins=cors_origins,
        cors_allow_credentials=cors_allow_credentials,
        log_level=_parse_log_level(os.getenv("LOG_LEVEL")),
        db_init=db_init,
    )


settings = load_settings()
