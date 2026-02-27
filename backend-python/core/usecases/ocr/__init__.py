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
    "list_ocr_profiles_for_api",
    "mark_ocr_availability",
    "run_ocr_box",
]


def run_ocr_box(*args, **kwargs):
    # Import lazily to avoid eager manga-ocr model loading during module import.
    from .engine import run_ocr_box as _run_ocr_box

    return _run_ocr_box(*args, **kwargs)
