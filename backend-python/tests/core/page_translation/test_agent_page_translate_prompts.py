# backend-python/tests/core/page_translation/test_agent_page_translate_prompts.py
"""Unit tests for page-translate prompt payload shaping and truncation.

What is tested:
- Merge-stage prompt construction caps oversized stage-1 payload sections.
- Prior memory blocks are clipped to bounded prompt sizes.

How it is tested:
- Build prompt payloads with intentionally oversized in-memory inputs.
- Parse the emitted JSON code block and assert structural caps.
"""

from __future__ import annotations

import json
import re

from core.usecases.page_translation.prompts import build_state_merge_prompt_payload


def test_build_state_merge_prompt_payload_trims_large_inputs() -> None:
    stage1_result = {
        "boxes": [
            {
                "box_ids": [index + 1],
                "ocr_profile_id": "openai_quality_ocr",
                "ocr_text": f"BOX_OCR_{index}_" + ("x" * 400),
                "speaker_id": f"char_{index}",
                "addressee_id": "unknown",
                "speaker_gender": "unknown",
                "speaker_visual_cues": "cue " + ("y" * 300),
                "translation": f"BOX_TRANSLATION_{index}_" + ("z" * 400),
            }
            for index in range(300)
        ],
        "no_text_boxes": list(range(1, 500)),
        "image_summary": "summary " + ("i" * 2000),
        "page_events": [f"EVENT_{idx}_" + ("e" * 200) for idx in range(60)],
        "page_characters_detected": [
            {
                "speaker_id": f"CHAR_{idx}",
                "speaker_gender": "unknown",
                "speaker_visual_cues": "visual " + ("v" * 260),
            }
            for idx in range(80)
        ],
    }

    system_prompt, user_prompt = build_state_merge_prompt_payload(
        source_language="Japanese",
        target_language="English",
        prior_context_summary="story " + ("s" * 10_000),
        prior_characters=[{"name": "A", "info": "i" * 10_000}],
        prior_open_threads=["t" * 10_000],
        prior_glossary=[{"term": "x", "translation": "y", "note": "n" * 10_000}],
        stage1_result=stage1_result,
    )

    assert "..." in system_prompt

    match = re.search(r"```json\n(.*?)\n```", user_prompt, flags=re.DOTALL)
    assert match is not None
    stage1_json_text = (match.group(1) if match else "").strip()
    stage1_json = json.loads(stage1_json_text)

    assert len(stage1_json["boxes"]) == 120
    assert len(stage1_json["no_text_boxes"]) == 240
    assert len(stage1_json["page_events"]) == 20
    assert len(stage1_json["page_characters_detected"]) == 40
