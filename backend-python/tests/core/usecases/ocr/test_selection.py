# backend-python/tests/core/usecases/ocr/test_selection.py
"""Unit tests for shared OCR candidate selection helpers."""

from __future__ import annotations

from core.usecases.ocr.selection import choose_preferred_ocr_text, select_box_ocr_texts


def test_choose_preferred_ocr_text_prefers_requested_profiles() -> None:
    chosen = choose_preferred_ocr_text(
        {
            "manga_ocr_default": "fallback text",
            "openai_fast_ocr": "preferred text",
        },
        preferred_profile_ids=["openai_fast_ocr", "manga_ocr_default"],
    )

    assert chosen == "preferred text"


def test_select_box_ocr_texts_falls_back_to_first_non_empty_candidate() -> None:
    selected = select_box_ocr_texts(
        {
            3: {
                "openai_fast_ocr": "",
                "manga_ocr_default": "chosen text",
            },
            4: {
                "openai_fast_ocr": "secondary text",
            },
        },
        box_ids=[3, 4, 4, 0],
        preferred_profile_ids=["openai_fast_ocr"],
    )

    assert selected == {
        3: "chosen text",
        4: "secondary text",
    }
