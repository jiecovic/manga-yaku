# backend-python/tests/core/page_translation/test_agent_page_translate_helpers.py
"""Unit coverage for page-translate helper sanitizers and OCR consensus guards.

What is tested:
- `normalize_translate_stage_result` cleans malformed stage-1 payload fields.
- `apply_no_text_consensus_guard` enforces conservative no-text outcomes.

How it is tested:
- Pure in-memory dictionaries with intentionally invalid/mixed types.
- No DB, no filesystem, and no external LLM/API calls.
"""

from __future__ import annotations

from core.usecases.page_translation.schema import (
    apply_no_text_consensus_guard,
    normalize_translate_stage_result,
)


def test_normalize_translate_stage_result_cleans_payload() -> None:
    raw = {
        "boxes": [
            {
                "box_ids": [1, 2, 2, "3", "bad"],
                "ocr_profile_id": "",
                "ocr_text": " jp ",
                "speaker_id": "",
                "addressee_id": None,
                "speaker_gender": "not-a-valid-gender",
                "speaker_visual_cues": " cue ",
                "referent_id": "",
                "referent_gender": "invalid",
                "translation": " line ",
            },
            {"box_ids": "invalid"},
        ],
        "no_text_boxes": ["2", 0, None, "bad"],
        "image_summary": " summary ",
        "page_events": [" a ", "", "  "],
        "page_characters_detected": [
            {
                "speaker_id": "",
                "speaker_gender": "invalid",
                "speaker_visual_cues": " person ",
            }
        ],
    }

    result = normalize_translate_stage_result(raw)
    assert result["no_text_boxes"] == [2]
    assert len(result["boxes"]) == 1

    box = result["boxes"][0]
    assert box["box_ids"] == [1, 3]
    assert box["ocr_profile_id"] == "unknown"
    assert box["ocr_text"] == "jp"
    assert box["speaker_id"] == "unknown"
    assert box["addressee_id"] == ""
    assert box["speaker_gender"] == "unknown"
    assert box["speaker_visual_cues"] == "cue"
    assert box["referent_id"] == "unknown"
    assert box["referent_gender"] == "unknown"
    assert box["translation"] == "line"

    assert result["image_summary"] == "summary"
    assert result["page_events"] == ["a"]
    assert result["page_characters_detected"] == [
        {
            "speaker_id": "unknown",
            "speaker_gender": "unknown",
            "speaker_visual_cues": "person",
        }
    ]


def test_consensus_guard_marks_weak_short_local_hit_as_no_text() -> None:
    stage1 = {
        "boxes": [
            {
                "box_ids": [1],
                "ocr_profile_id": "manga_ocr_default",
                "ocr_text": "aa",
                "translation": "rumble",
            }
        ],
        "no_text_boxes": [],
    }
    input_boxes = [
        {
            "box_index": 1,
            "ocr_no_text_profiles": ["openai_fast_ocr", "openai_quality_ocr"],
            "ocr_candidates": [{"profile_id": "manga_ocr_default", "text": "aa"}],
        }
    ]
    ocr_profiles = [
        {"id": "manga_ocr_default", "model": "manga_ocr", "hint": "weak empty-crop detection"},
        {"id": "openai_fast_ocr", "model": "gpt-4.1-mini", "hint": "remote"},
        {"id": "openai_quality_ocr", "model": "gpt-5-mini", "hint": "remote"},
    ]

    adjusted, moved = apply_no_text_consensus_guard(
        stage1_result=stage1,
        input_boxes=input_boxes,
        ocr_profiles=ocr_profiles,
    )
    assert moved == [1]
    assert adjusted["boxes"] == []
    assert adjusted["no_text_boxes"] == [1]


def test_consensus_guard_keeps_entry_when_remote_text_exists() -> None:
    stage1 = {
        "boxes": [
            {
                "box_ids": [1],
                "ocr_profile_id": "manga_ocr_default",
                "ocr_text": "aa",
                "translation": "rumble",
            }
        ],
        "no_text_boxes": [],
    }
    input_boxes = [
        {
            "box_index": 1,
            "ocr_no_text_profiles": ["openai_fast_ocr", "openai_quality_ocr"],
            "ocr_candidates": [
                {"profile_id": "manga_ocr_default", "text": "aa"},
                {"profile_id": "openai_fast_ocr", "text": "text exists"},
            ],
        }
    ]
    ocr_profiles = [
        {"id": "manga_ocr_default", "model": "manga_ocr", "hint": "weak empty crop detection"},
        {"id": "openai_fast_ocr", "model": "gpt-4.1-mini", "hint": "remote"},
        {"id": "openai_quality_ocr", "model": "gpt-5-mini", "hint": "remote"},
    ]

    adjusted, moved = apply_no_text_consensus_guard(
        stage1_result=stage1,
        input_boxes=input_boxes,
        ocr_profiles=ocr_profiles,
    )
    assert moved == []
    assert len(adjusted["boxes"]) == 1
    assert adjusted["no_text_boxes"] == []


def test_consensus_guard_drops_hallucinated_text_on_remote_no_text() -> None:
    stage1 = {
        "boxes": [
            {
                "box_ids": [1],
                "ocr_profile_id": "openai_quality_ocr",
                "ocr_text": "ウゥ",
                "translation": "vrrr",
            }
        ],
        "no_text_boxes": [],
    }
    input_boxes = [
        {
            "box_index": 1,
            "ocr_no_text_profiles": ["openai_fast_ocr", "openai_quality_ocr"],
            "ocr_candidates": [{"profile_id": "manga_ocr_default", "text": "ガス"}],
        }
    ]
    ocr_profiles = [
        {
            "id": "manga_ocr_default",
            "model": "manga_ocr",
            "hint": "weak empty-crop detection",
        },
        {"id": "openai_fast_ocr", "model": "gpt-4.1-mini", "hint": "remote"},
        {"id": "openai_quality_ocr", "model": "gpt-5-mini", "hint": "remote"},
    ]

    adjusted, moved = apply_no_text_consensus_guard(
        stage1_result=stage1,
        input_boxes=input_boxes,
        ocr_profiles=ocr_profiles,
    )
    assert moved == [1]
    assert adjusted["boxes"] == []
    assert adjusted["no_text_boxes"] == [1]
