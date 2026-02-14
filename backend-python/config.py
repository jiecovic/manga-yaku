# backend-python/config.py
import os
from pathlib import Path

from settings import settings

# -----------------------------
# Paths (cwd-independent)
# -----------------------------

# Folder where this file lives, e.g. .../mangayaku-ai/python-backend
BACKEND_DIR = Path(__file__).resolve().parent

# Project root: one level above backend, e.g. .../mangayaku-ai
PROJECT_ROOT = BACKEND_DIR.parent

# Data directories (shared for all backend modules)
DATA_DIR = PROJECT_ROOT / "data"
VOLUMES_ROOT = DATA_DIR / "volumes"
JSON_ROOT = DATA_DIR / "json"
DEBUG_LOGS_DIR = DATA_DIR / "logs"
AGENT_DEBUG_DIR = DEBUG_LOGS_DIR / "agent"
MODELS_ROOT = PROJECT_ROOT / "models"

TRAINING_DATA_ROOT = PROJECT_ROOT / "training-data"
TRAINING_SOURCES_ROOT = TRAINING_DATA_ROOT / "sources"
TRAINING_PREPARED_ROOT = TRAINING_DATA_ROOT / "prepared"
TRAINING_RUNS_ROOT = TRAINING_DATA_ROOT / "runs"
ULTRALYTICS_ROOT = TRAINING_DATA_ROOT / "ultralytics"
ULTRALYTICS_WEIGHTS_ROOT = ULTRALYTICS_ROOT / "weights"
ULTRALYTICS_RUNS_ROOT = TRAINING_RUNS_ROOT
ULTRALYTICS_DATASETS_ROOT = ULTRALYTICS_ROOT / "datasets"


OPENAI_API_KEY = settings.openai_api_key
DATABASE_URL = settings.database_url

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-5.2")
AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.2"))
AGENT_MAX_OUTPUT_TOKENS = int(os.getenv("AGENT_MAX_OUTPUT_TOKENS", "512"))
AGENT_TRANSLATE_MAX_OUTPUT_TOKENS = int(
    os.getenv("AGENT_TRANSLATE_MAX_OUTPUT_TOKENS", "2048")
)
AGENT_MAX_MESSAGE_CHARS = int(os.getenv("AGENT_MAX_MESSAGE_CHARS", "2000"))
AGENT_REASONING_EFFORT = os.getenv("AGENT_REASONING_EFFORT", "medium").strip().lower()
AGENT_TRANSLATE_REASONING_EFFORT = os.getenv(
    "AGENT_TRANSLATE_REASONING_EFFORT", "low"
).strip().lower()
AGENT_PROMPT_FILE = os.getenv("AGENT_PROMPT_FILE", "agent_default.yml")
AGENT_MODELS = [
    item.strip()
    for item in os.getenv(
        "AGENT_MODELS",
        "gpt-5.2,gpt-5.2-pro,gpt-5-mini,gpt-5-nano,gpt-4.1,gpt-4.1-mini,gpt-4o,gpt-4o-mini",
    ).split(",")
    if item.strip()
]


# -----------------------------
# Security helpers
# -----------------------------

def safe_join(root: Path, *parts: str) -> Path:
    """
    Resolve a path under root and reject path traversal.
    """
    root_resolved = root.resolve()
    candidate = root.joinpath(*parts)
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Unsafe path traversal detected") from exc
    return resolved


def configure_ultralytics_settings() -> None:
    os.environ["YOLO_CONFIG_DIR"] = str(ULTRALYTICS_ROOT)
    try:
        from ultralytics.utils import SETTINGS
    except Exception:
        return

    for path in (ULTRALYTICS_WEIGHTS_ROOT, ULTRALYTICS_DATASETS_ROOT, ULTRALYTICS_RUNS_ROOT):
        path.mkdir(parents=True, exist_ok=True)

    SETTINGS.update(
        weights_dir=str(ULTRALYTICS_WEIGHTS_ROOT),
        runs_dir=str(ULTRALYTICS_RUNS_ROOT),
        datasets_dir=str(ULTRALYTICS_DATASETS_ROOT),
    )


# -----------------------------
# Runtime flags
# -----------------------------

DEBUG_PROMPTS = settings.debug_prompts

