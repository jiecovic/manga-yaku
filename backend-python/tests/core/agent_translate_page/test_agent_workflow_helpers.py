# backend-python/tests/core/agent_translate_page/test_agent_workflow_helpers.py
"""Unit tests for workflow helper mapping and normalization functions.

What is tested:
- OCR profile resolution (dedupe, unknown filtering, disabled filtering).
- Translation input box construction from persisted page/box records.
- Translation payload application back onto page boxes.

How it is tested:
- In-memory payloads plus targeted patching of write-side helper functions.
- Focused on helper behavior; DB/worker execution is not exercised here.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.workflows.agent_translate_page.helpers import (
    apply_translation_payload,
    build_translation_boxes,
    resolve_ocr_profiles,
)


class ResolveOcrProfilesTests(unittest.TestCase):
    def test_resolve_ocr_profiles_filters_disabled_and_unknown(self) -> None:
        # Duplicates should collapse, disabled profiles should drop, and
        # unknown ids should fail closed instead of leaking through.
        payload = {"ocrProfiles": ["p1", "p2", "p1", "missing"]}

        def fake_get(profile_id: str) -> dict:
            if profile_id == "p1":
                return {"enabled": True}
            if profile_id == "p2":
                return {"enabled": False}
            raise RuntimeError("unknown profile")

        with (
            patch(
                "core.workflows.agent_translate_page.helpers.agent_enabled_ocr_profiles",
                return_value=[],
            ),
            patch(
                "core.workflows.agent_translate_page.helpers.get_ocr_profile",
                side_effect=fake_get,
            ),
        ):
            resolved = resolve_ocr_profiles(payload)

        self.assertEqual(resolved, ["p1"])

    def test_resolve_ocr_profiles_uses_fallback_default(self) -> None:
        with (
            patch(
                "core.workflows.agent_translate_page.helpers.agent_enabled_ocr_profiles",
                return_value=[],
            ),
            patch(
                "core.workflows.agent_translate_page.helpers.get_ocr_profile",
                return_value={"enabled": True},
            ),
        ):
            resolved = resolve_ocr_profiles({})

        self.assertEqual(resolved, ["manga_ocr_default"])

    def test_resolve_ocr_profiles_raises_when_none_enabled(self) -> None:
        with (
            patch(
                "core.workflows.agent_translate_page.helpers.agent_enabled_ocr_profiles",
                return_value=[],
            ),
            patch(
                "core.workflows.agent_translate_page.helpers.get_ocr_profile",
                return_value={"enabled": False},
            ),
        ):
            with self.assertRaises(RuntimeError):
                resolve_ocr_profiles({})


class BuildTranslationBoxesTests(unittest.TestCase):
    def test_build_translation_boxes_assigns_unique_box_indexes(self) -> None:
        # Duplicate orderIndex values must be re-assigned deterministically
        # so every output entry keeps a unique id space for the LLM stage.
        text_boxes = [
            {"id": 101, "orderIndex": 2},
            {"id": 102, "orderIndex": 2},
            {"id": 103, "orderIndex": 0},
        ]
        candidates = {
            101: {"manga_ocr_default": "foo"},
            102: {"openai_quality_ocr": "bar"},
            103: {},
        }
        payload_boxes, box_index_map = build_translation_boxes(
            text_boxes=text_boxes,
            candidates=candidates,
            no_text_candidates={},
            error_candidates={},
            invalid_candidates={},
            llm_profiles=set(),
        )

        indexes = [int(item["box_index"]) for item in payload_boxes]
        self.assertEqual(indexes, [2, 3, 4])
        self.assertEqual(box_index_map, {2: 101, 3: 102, 4: 103})

    def test_build_translation_boxes_filters_llm_error_buckets(self) -> None:
        text_boxes = [{"id": 1, "orderIndex": 1}]
        payload_boxes, _ = build_translation_boxes(
            text_boxes=text_boxes,
            candidates={1: {"manga_ocr_default": "text"}},
            no_text_candidates={},
            error_candidates={1: {"openai_fast_ocr", "local_bad"}},
            invalid_candidates={1: {"openai_fast_ocr", "local_invalid"}},
            llm_profiles={"openai_fast_ocr"},
        )

        self.assertEqual(payload_boxes[0].get("ocr_error_profiles"), ["local_bad"])
        self.assertEqual(payload_boxes[0].get("ocr_invalid_profiles"), ["local_invalid"])


class ApplyTranslationPayloadTests(unittest.TestCase):
    def test_apply_translation_payload_merges_and_deletes_explicit_targets(self) -> None:
        # Boxes merged into one translated line should keep a single survivor.
        # Deletions should be explicit via no_text + merged ids.
        text_boxes = [{"id": 10}, {"id": 20}, {"id": 30}, {"id": 40}]
        box_index_map = {1: 10, 2: 20, 3: 30, 4: 40}
        translation_payload = {
            "boxes": [
                {
                    "box_ids": [1, 2],
                    "ocr_text": "jp line",
                    "translation": "translated",
                },
            ],
            "no_text_boxes": [3, 4],
        }

        with (
            patch(
                "core.workflows.agent_translate_page.helpers.set_box_ocr_text_by_id",
            ) as set_ocr,
            patch(
                "core.workflows.agent_translate_page.helpers.set_box_translation_by_id",
            ) as set_translation,
            patch(
                "core.workflows.agent_translate_page.helpers.delete_boxes_by_ids",
            ) as delete_boxes,
            patch(
                "core.workflows.agent_translate_page.helpers.set_box_order_for_type",
                return_value=True,
            ) as set_order,
        ):
            result = apply_translation_payload(
                volume_id="vol",
                filename="001.jpg",
                text_boxes=text_boxes,
                box_index_map=box_index_map,
                translation_payload=translation_payload,
            )

        set_ocr.assert_called_once_with("vol", "001.jpg", box_id=10, ocr_text="jp line")
        set_translation.assert_called_once_with(
            "vol",
            "001.jpg",
            box_id=10,
            translation="translated",
        )
        set_order.assert_called_once_with(
            "vol",
            "001.jpg",
            box_type="text",
            ordered_ids=[10],
        )

        deleted_ids: set[int] = set()
        for call in delete_boxes.call_args_list:
            args = call.args
            if len(args) >= 3 and isinstance(args[2], list):
                deleted_ids.update(int(item) for item in args[2])
        self.assertEqual(deleted_ids, {20, 30, 40})

        self.assertEqual(result["updated"], 1)
        self.assertTrue(result["orderApplied"])
        self.assertEqual(result["processed"], 4)
        self.assertEqual(result["total"], 4)

    def test_apply_translation_payload_warns_on_missing_coverage(self) -> None:
        text_boxes = [{"id": 10}, {"id": 20}]
        box_index_map = {1: 10, 2: 20}
        translation_payload = {
            "boxes": [{"box_ids": [1], "ocr_text": "a", "translation": "b"}],
            "no_text_boxes": [],
        }

        with (
            patch(
                "core.workflows.agent_translate_page.helpers.set_box_ocr_text_by_id",
            ) as set_ocr,
            patch(
                "core.workflows.agent_translate_page.helpers.set_box_translation_by_id",
            ) as set_translation,
            patch(
                "core.workflows.agent_translate_page.helpers.delete_boxes_by_ids",
            ) as delete_boxes,
            patch(
                "core.workflows.agent_translate_page.helpers.set_box_order_for_type",
                return_value=False,
            ) as set_order,
        ):
            result = apply_translation_payload(
                volume_id="vol",
                filename="001.jpg",
                text_boxes=text_boxes,
                box_index_map=box_index_map,
                translation_payload=translation_payload,
            )

        set_ocr.assert_called_once_with("vol", "001.jpg", box_id=10, ocr_text="a")
        set_translation.assert_called_once_with(
            "vol",
            "001.jpg",
            box_id=10,
            translation="b",
        )
        set_order.assert_called_once_with(
            "vol",
            "001.jpg",
            box_type="text",
            ordered_ids=[10, 20],
        )
        delete_boxes.assert_not_called()
        self.assertIn("coverageWarning", result)
        self.assertIn("omitted indices", result["coverageWarning"])

    def test_apply_translation_payload_raises_on_duplicate_coverage(self) -> None:
        text_boxes = [{"id": 10}, {"id": 20}]
        box_index_map = {1: 10, 2: 20}
        translation_payload = {
            "boxes": [{"box_ids": [1], "ocr_text": "a", "translation": "b"}],
            "no_text_boxes": [1, 2],
        }

        with self.assertRaisesRegex(RuntimeError, "duplicate indices"):
            apply_translation_payload(
                volume_id="vol",
                filename="001.jpg",
                text_boxes=text_boxes,
                box_index_map=box_index_map,
                translation_payload=translation_payload,
            )
