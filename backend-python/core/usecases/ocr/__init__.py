# backend-python/core/usecases/ocr/__init__.py
"""Public exports for OCR usecases."""

from .profiles import (
    OCR_PROFILES,
    OcrProfile,
    get_ocr_profile,
    list_ocr_profiles_for_api,
    mark_ocr_availability,
)

__all__ = [
    "OCR_PROFILES",
    "OcrProfile",
    "get_ocr_profile",
    "initialize_ocr_runtime",
    "list_ocr_profiles_for_api",
    "mark_ocr_availability",
    "run_ocr_box",
]


def run_ocr_box(*args, **kwargs):
    # Import lazily to avoid eager manga-ocr model loading during module import.
    from .engine import run_ocr_box as _run_ocr_box

    return _run_ocr_box(*args, **kwargs)


def initialize_ocr_runtime() -> None:
    # Ensure runtime capability flags (and optional model preload side effects)
    # are initialized before serving profile availability to the UI.
    from . import engine as _engine  # noqa: F401
