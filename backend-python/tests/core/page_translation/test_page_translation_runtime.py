# backend-python/tests/core/page_translation/test_page_translation_runtime.py
"""Unit tests for page-translation runtime coverage warnings."""

from __future__ import annotations

from unittest.mock import patch

from core.usecases.page_translation.runtime import run_page_translation_stage


class _DummyImage:
    size = (1200, 1800)


def test_run_page_translation_stage_warns_on_missing_box_coverage() -> None:
    stage1_result = {
        "boxes": [
            {
                "box_ids": [1],
                "ocr_profile_id": "manga_ocr_default",
                "ocr_text": "jp",
                "speaker_id": "unknown",
                "addressee_id": "",
                "speaker_gender": "unknown",
                "speaker_visual_cues": "",
                "referent_id": "unknown",
                "referent_gender": "unknown",
                "translation": "en",
            }
        ],
        "no_text_boxes": [],
        "image_summary": "summary",
        "page_events": [],
        "page_characters_detected": [],
    }
    stage1_debug = {
        "model": "gpt-5-mini",
        "attempt_count": 2,
        "latency_ms": 10,
        "finish_reason": "incomplete:max_output_tokens",
        "params": {"max_output_tokens": 4096},
    }
    stage2_result = {
        "characters": [],
        "open_threads": [],
        "glossary": [],
        "story_summary": "",
    }
    stage2_debug = {
        "model": "gpt-5-mini",
        "attempt_count": 1,
        "latency_ms": 5,
        "finish_reason": "stop",
        "params": {"max_output_tokens": 768},
    }

    with (
        patch("core.usecases.page_translation.runtime.has_openai_sdk", return_value=True),
        patch(
            "core.usecases.page_translation.runtime.build_translate_stage_prompt_payload",
            return_value=("sys", "user"),
        ),
        patch(
            "core.usecases.page_translation.runtime.build_state_merge_prompt_payload",
            return_value=("merge-sys", "merge-user"),
        ),
        patch(
            "core.usecases.page_translation.runtime.load_volume_image", return_value=_DummyImage()
        ),
        patch(
            "core.usecases.page_translation.runtime.resize_for_llm",
            side_effect=lambda image: image,
        ),
        patch(
            "core.usecases.page_translation.runtime.encode_image_data_url",
            return_value="data:image/png;base64,abc",
        ),
        patch("core.usecases.page_translation.runtime.create_openai_client", return_value=object()),
        patch(
            "core.usecases.page_translation.runtime.run_structured_call",
            side_effect=[(stage1_result, stage1_debug), (stage2_result, stage2_debug)],
        ),
        patch("core.usecases.page_translation.runtime.logger.warning") as logger_warning,
    ):
        result = run_page_translation_stage(
            volume_id="vol",
            filename="001.jpg",
            boxes=[{"box_index": 1}, {"box_index": 2}],
            ocr_profiles=[{"id": "manga_ocr_default"}],
            source_language="Japanese",
            target_language="English",
            model_id="gpt-5-mini",
        )

    assert result["boxes"] == stage1_result["boxes"]
    assert result["_stage_meta"]["translate_page"]["coverage_summary"] == {
        "expected_box_count": 2,
        "covered_box_count": 1,
        "missing_box_ids": [2],
        "unexpected_box_ids": [],
        "duplicate_box_ids": [],
        "is_complete": False,
    }
    assert result["_stage_meta"]["translate_page"]["warnings"] == [
        "Translate stage output omitted 1 input boxes: [2]. The model output was truncated; consider increasing page-translation max_output_tokens."
    ]
    logger_warning.assert_called_once()
