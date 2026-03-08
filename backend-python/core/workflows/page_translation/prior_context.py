# backend-python/core/workflows/page_translation/prior_context.py
"""Prior context loading for the page-translation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from infra.db.store_context import get_volume_context


@dataclass(frozen=True)
class PriorContextSnapshot:
    summary: str
    characters: list[Any]
    open_threads: list[Any]
    glossary: list[Any]


def load_prior_context(volume_id: str) -> PriorContextSnapshot:
    volume_context = get_volume_context(volume_id) or {}
    prior_characters = volume_context.get("active_characters")
    if not isinstance(prior_characters, list):
        prior_characters = []
    prior_open_threads = volume_context.get("open_threads")
    if not isinstance(prior_open_threads, list):
        prior_open_threads = []
    prior_glossary = volume_context.get("glossary")
    if not isinstance(prior_glossary, list):
        prior_glossary = []
    return PriorContextSnapshot(
        summary=str(volume_context.get("rolling_summary") or ""),
        characters=prior_characters,
        open_threads=prior_open_threads,
        glossary=prior_glossary,
    )
