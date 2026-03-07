# backend-python/tests/core/usecases/test_translate_stage_prompt_payload.py
"""Tests for page-translation prompt safeguards."""

from __future__ import annotations

from core.usecases.page_translation.prompts import build_translate_stage_prompt_payload


def test_translate_stage_prompt_discourages_forced_gendered_pronouns() -> None:
    system_prompt, _ = build_translate_stage_prompt_payload(
        source_language="Japanese",
        target_language="English",
        boxes=[],
        ocr_profiles=[],
        prior_context_summary=None,
        prior_characters=None,
        prior_open_threads=None,
        prior_glossary=None,
    )

    assert "Do not introduce gendered pronouns" in system_prompt
    assert '"that person"' in system_prompt
    assert "not as permission to force a gendered pronoun" in system_prompt
    assert (
        "First identify the page-local cast from the image before translating lines"
        in system_prompt
    )
    assert (
        "Page-local entity resolution from Mode 0 takes precedence over prior lore" in system_prompt
    )
    assert "referent_id and referent_gender" in system_prompt
    assert "emit attribution fields first and translation last" in system_prompt
