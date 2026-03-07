# backend-python/tests/core/usecases/test_agent_prompt_defaults.py
# backend-python/tests/core/usecases/test_agent_prompt_defaults.py
"""Tests for shared agent translation language defaults."""

from __future__ import annotations

from config import TRANSLATION_SOURCE_LANGUAGE, TRANSLATION_TARGET_LANGUAGE
from core.usecases.agent.engine import _load_system_prompt
from core.workflows.agent_translate_page.types import AgentTranslatePageRequest


def test_load_system_prompt_renders_shared_language_defaults() -> None:
    prompt = _load_system_prompt()

    assert TRANSLATION_SOURCE_LANGUAGE in prompt
    assert TRANSLATION_TARGET_LANGUAGE in prompt
    assert "{{SOURCE_LANG}}" not in prompt
    assert "{{TARGET_LANG}}" not in prompt


def test_agent_translate_request_uses_shared_language_defaults() -> None:
    request = AgentTranslatePageRequest.from_payload(
        {
            "volumeId": "vol-a",
            "filename": "001.jpg",
        }
    )

    assert request.source_language == TRANSLATION_SOURCE_LANGUAGE
    assert request.target_language == TRANSLATION_TARGET_LANGUAGE


def test_load_system_prompt_mentions_page_memory_tools_and_verification() -> None:
    prompt = _load_system_prompt()

    assert "get_page_memory" in prompt
    assert "update_page_memory" in prompt
    assert "verify saved results" in prompt
    assert "prefer translate_active_page" in prompt
    assert "use primitive tools only if you need follow-up inspection" in prompt
    assert "If all current boxes already have translations" in prompt
    assert "Do not describe the page as translated yet" in prompt
    assert (
        "Only claim the page was already translated if translate_active_page "
        "returns status=already_translated" in prompt
    )
    assert "force_rerun=true" in prompt
    assert "do not ask the user to upload/share another screenshot" in prompt
    assert "If a visual check is still needed, inspect one box crop at a time" in prompt
    assert "do not call view_text_box" in prompt.lower()
    assert "Avoid requesting multiple box-image crops in parallel" in prompt
    assert "detect_missing_boxes" not in prompt
    assert "detection likely missed text" in prompt
    assert "run the page-translation workflow" in prompt
