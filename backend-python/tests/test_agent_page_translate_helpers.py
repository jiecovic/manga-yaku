"""Unit tests for page-translate helper sanitizers and OCR consensus guards.

These tests use deterministic in-memory payloads to validate normalization and
no-text override logic without calling external services.
"""

from __future__ import annotations

import unittest

from core.usecases.agent.page_translate_helpers import (
    apply_no_text_consensus_guard,
    normalize_translate_stage_result,
)


class NormalizeTranslateStageResultTests(unittest.TestCase):
    def test_normalize_translate_stage_result_cleans_payload(self) -> None:
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
        self.assertEqual(result["no_text_boxes"], [2])
        self.assertEqual(len(result["boxes"]), 1)

        box = result["boxes"][0]
        self.assertEqual(box["box_ids"], [1, 3])
        self.assertEqual(box["ocr_profile_id"], "unknown")
        self.assertEqual(box["ocr_text"], "jp")
        self.assertEqual(box["speaker_id"], "unknown")
        self.assertEqual(box["addressee_id"], "")
        self.assertEqual(box["speaker_gender"], "unknown")
        self.assertEqual(box["speaker_visual_cues"], "cue")
        self.assertEqual(box["translation"], "line")

        self.assertEqual(result["image_summary"], "summary")
        self.assertEqual(result["page_events"], ["a"])
        self.assertEqual(
            result["page_characters_detected"],
            [
                {
                    "speaker_id": "unknown",
                    "speaker_gender": "unknown",
                    "speaker_visual_cues": "person",
                }
            ],
        )


class NoTextConsensusGuardTests(unittest.TestCase):
    def test_consensus_guard_marks_weak_short_local_hit_as_no_text(self) -> None:
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
        self.assertEqual(moved, [1])
        self.assertEqual(adjusted["boxes"], [])
        self.assertEqual(adjusted["no_text_boxes"], [1])

    def test_consensus_guard_keeps_entry_when_remote_text_exists(self) -> None:
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
        self.assertEqual(moved, [])
        self.assertEqual(len(adjusted["boxes"]), 1)
        self.assertEqual(adjusted["no_text_boxes"], [])
