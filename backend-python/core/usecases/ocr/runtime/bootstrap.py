# backend-python/core/usecases/ocr/runtime/bootstrap.py
"""One-time OCR runtime initialization and optional dependency loading."""

from __future__ import annotations

import logging
from typing import Any

from config import OPENAI_API_KEY
from infra.llm import has_openai_sdk
from infra.logging.correlation import append_correlation

from ..profiles.catalog import mark_ocr_availability

logger = logging.getLogger(__name__)

_runtime_initialized = False
_manga_ocr: Any | None = None
_manga_ocr_error: Exception | None = None


def initialize_ocr_runtime() -> None:
    """Initialize OCR runtime side effects once before profile reads or OCR runs."""
    global _runtime_initialized, _manga_ocr, _manga_ocr_error
    if _runtime_initialized:
        return

    try:
        from manga_ocr import MangaOcr  # type: ignore

        _manga_ocr = MangaOcr()
        _manga_ocr_error = None
    except Exception as exc:  # pragma: no cover
        _manga_ocr = None
        _manga_ocr_error = exc

    has_sdk = has_openai_sdk()
    has_llm_ocr = has_sdk and bool(OPENAI_API_KEY)

    if has_sdk and not OPENAI_API_KEY:
        logger.warning(
            append_correlation(
                "OPENAI_API_KEY not set; OpenAI OCR profiles disabled",
                {"component": "ocr.runtime"},
            )
        )
    elif not has_sdk:
        logger.warning(
            append_correlation(
                "OpenAI SDK not available; OpenAI OCR profiles disabled",
                {"component": "ocr.runtime"},
            )
        )

    mark_ocr_availability(
        has_manga_ocr=_manga_ocr is not None,
        has_llm_ocr=has_llm_ocr,
    )
    _runtime_initialized = True


def get_manga_ocr_runtime() -> tuple[Any | None, Exception | None]:
    """Return the optional manga-ocr instance and any captured init error."""
    initialize_ocr_runtime()
    return _manga_ocr, _manga_ocr_error
