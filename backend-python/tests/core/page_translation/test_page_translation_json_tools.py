# backend-python/tests/core/page_translation/test_page_translation_json_tools.py
"""Tests for page-translation JSON extraction helpers."""

from core.usecases.page_translation.schema.json_tools import extract_json


def test_extract_json_repairs_common_llm_json_damage() -> None:
    raw = """
    text before
    {"boxes":[{"source_text":"a" "target_text":"b",}],"no_text_boxes":[]}
    text after
    """

    parsed = extract_json(raw)

    assert parsed == {
        "boxes": [{"source_text": "a", "target_text": "b"}],
        "no_text_boxes": [],
    }
