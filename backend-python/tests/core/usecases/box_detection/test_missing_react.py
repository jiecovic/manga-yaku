# backend-python/tests/core/usecases/box_detection/test_missing_react.py
"""Tests for missing-box ReAct loop retry and persistence behavior."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from PIL import Image

from core.usecases.box_detection.missing_react import detect_missing_text_boxes_react
from core.usecases.box_detection.missing_react_llm import _extract_json_object


class MissingReactTests(unittest.TestCase):
    def test_extract_json_object_salvages_complete_candidates_from_partial_output(self) -> None:
        raw = (
            '{"candidates":[{"hint_text":"A","reason":"ok","x":1,"y":2,"width":3,"height":4},'
            '{"hint_text":"B","reason":"cut'
        )

        parsed = _extract_json_object(raw)

        self.assertEqual(len(parsed["candidates"]), 1)
        self.assertEqual(parsed["candidates"][0]["hint_text"], "A")

    def test_malformed_propose_response_falls_back_to_zero_candidates(self) -> None:
        source_image = Image.new("RGB", (100, 100), color="white")

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                side_effect=ValueError("bad json"),
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=2,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["proposed_count"], 0)
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["created_count"], 0)

    def test_verification_error_reports_error_kind(self) -> None:
        source_image = Image.new("RGB", (100, 100), color="white")
        runtime_events: list[dict[str, Any]] = []

        def _on_event(event: dict[str, Any]) -> None:
            runtime_events.append(dict(event))

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "target",
                        "reason": "missing text",
                        "x": 10.0,
                        "y": 10.0,
                        "width": 30.0,
                        "height": 20.0,
                    }
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                side_effect=ValueError("No JSON object found in model response"),
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=1,
                max_attempts_per_candidate=1,
                on_runtime_event=_on_event,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["accepted_count"], 0)
        error_events = [
            event
            for event in runtime_events
            if str(event.get("status") or "") == "verification_error"
        ]
        self.assertEqual(len(error_events), 1)
        self.assertEqual(error_events[0].get("error_kind"), "schema_parse_error")
        self.assertIn("No JSON object found", str(error_events[0].get("error_detail") or ""))

    def test_adjust_error_emits_runtime_event_before_fallback(self) -> None:
        source_image = Image.new("RGB", (100, 100), color="white")
        runtime_events: list[dict[str, Any]] = []

        def _on_event(event: dict[str, Any]) -> None:
            runtime_events.append(dict(event))

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "target",
                        "reason": "missing text",
                        "x": 10.0,
                        "y": 10.0,
                        "width": 30.0,
                        "height": 20.0,
                    }
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                side_effect=[
                    {
                        "contains_text": False,
                        "fully_inside_box": False,
                        "text_cut_off": True,
                        "confidence": 0.2,
                        "observed_text": "",
                        "reason": "missed",
                    },
                    {
                        "contains_text": True,
                        "fully_inside_box": True,
                        "text_cut_off": False,
                        "confidence": 0.95,
                        "observed_text": "target",
                        "reason": "accepted",
                    },
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._adjust_candidate_box",
                side_effect=RuntimeError("OpenAI adjust step failed"),
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_detection_run",
                return_value="run-1",
            ),
            patch(
                "core.usecases.box_detection.missing_react.replace_boxes_for_type",
                return_value=[],
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=1,
                max_attempts_per_candidate=2,
                on_runtime_event=_on_event,
            )

        self.assertEqual(result["status"], "ok")
        adjust_events = [
            event for event in runtime_events if str(event.get("status") or "") == "adjust_error"
        ]
        self.assertEqual(len(adjust_events), 1)
        self.assertEqual(adjust_events[0].get("error_kind"), "provider_error")
        self.assertIn("OpenAI adjust step failed", str(adjust_events[0].get("error_detail") or ""))

    def test_overlap_skip_retries_and_persists_only_accepted(self) -> None:
        source_image = Image.new("RGB", (100, 100), color="white")
        verify_attempts: list[int] = []
        persisted_boxes: list[dict[str, Any]] = []
        runtime_events: list[dict[str, Any]] = []

        def _on_event(event: dict[str, Any]) -> None:
            runtime_events.append(dict(event))

        def _replace_boxes_for_type(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            nonlocal persisted_boxes
            payload_boxes = list(kwargs.get("boxes") or [])
            persisted_boxes = [dict(item) for item in payload_boxes]
            return [
                {"id": idx + 1, **dict(item)}
                for idx, item in enumerate(payload_boxes)
            ]

        def _verify_candidate_crop(*args: Any, **kwargs: Any) -> dict[str, Any]:
            attempt_index = int(kwargs.get("attempt_index") or 0)
            verify_attempts.append(attempt_index)
            if len(verify_attempts) == 1:
                return {
                    "contains_text": False,
                    "fully_inside_box": False,
                    "matches_hint": False,
                    "tightness": 0.1,
                    "confidence": 0.05,
                    "observed_text": "",
                    "reason": "first try missed",
                }
            return {
                "contains_text": True,
                "fully_inside_box": True,
                "matches_hint": True,
                "tightness": 0.8,
                "confidence": 0.90,
                "observed_text": "sample",
                "reason": "accepted",
            }

        def _box_iou(a: dict[str, float], b: dict[str, float]) -> float:
            # Force one overlap event on a mid-retry geometry range.
            ax = float(a.get("x") or 0.0)
            if 17.0 <= ax <= 19.0:
                return 0.2
            return 0.0

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={
                    "boxes": [
                        {
                            "id": 1,
                            "type": "text",
                            "x": 0.0,
                            "y": 10.0,
                            "width": 20.0,
                            "height": 20.0,
                            "text": "",
                        }
                    ]
                },
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_detection_run",
                return_value="run-test-1",
            ),
            patch(
                "core.usecases.box_detection.missing_react.replace_boxes_for_type",
                side_effect=_replace_boxes_for_type,
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "sample",
                        "reason": "missing text",
                        # Starts adjacent to an existing box. Retry growth+shift can
                        # trigger overlap in mid-attempts before a later attempt clears it.
                        "x": 19.3,
                        "y": 10.0,
                        "width": 20.0,
                        "height": 20.0,
                    }
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                side_effect=_verify_candidate_crop,
            ),
            patch(
                "core.usecases.box_detection.missing_react._box_iou",
                side_effect=_box_iou,
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=1,
                max_attempts_per_candidate=4,
                overlap_iou_threshold=0.05,
                on_runtime_event=_on_event,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["rejected_count"], 0)
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(len(persisted_boxes), 1)
        self.assertGreaterEqual(len(verify_attempts), 2)
        verify_statuses = [
            str(event.get("status") or "")
            for event in runtime_events
            if str(event.get("phase") or "") == "verify"
        ]
        self.assertIn("overlap_skip", verify_statuses)
        self.assertIn("accepted", verify_statuses)

    def test_weak_observed_text_is_rejected_and_not_persisted(self) -> None:
        source_image = Image.new("RGB", (100, 100), color="white")
        persisted_boxes: list[dict[str, Any]] = []

        def _replace_boxes_for_type(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            nonlocal persisted_boxes
            payload_boxes = list(kwargs.get("boxes") or [])
            persisted_boxes = [dict(item) for item in payload_boxes]
            return [{"id": 1, **dict(item)} for item in payload_boxes]

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_detection_run",
                return_value="run-test-2",
            ),
            patch(
                "core.usecases.box_detection.missing_react.replace_boxes_for_type",
                side_effect=_replace_boxes_for_type,
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "シリウスKC",
                        "reason": "missing text",
                        "x": 30.0,
                        "y": 20.0,
                        "width": 30.0,
                        "height": 16.0,
                    }
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                return_value={
                    "contains_text": True,
                    "fully_inside_box": True,
                    "matches_hint": True,
                    "tightness": 0.75,
                    "confidence": 0.95,
                    "observed_text": "…KC",
                    "reason": "looks partial",
                },
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=1,
                max_attempts_per_candidate=1,
                min_confidence=0.75,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(len(persisted_boxes), 0)

    def test_retry_uses_adjusted_box_context(self) -> None:
        source_image = Image.new("RGB", (200, 200), color="white")
        persisted_boxes: list[dict[str, Any]] = []

        def _replace_boxes_for_type(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            nonlocal persisted_boxes
            payload_boxes = list(kwargs.get("boxes") or [])
            persisted_boxes = [dict(item) for item in payload_boxes]
            return [{"id": idx + 1, **dict(item)} for idx, item in enumerate(payload_boxes)]

        verify_results = [
            {
                "contains_text": False,
                "fully_inside_box": False,
                "matches_hint": False,
                "tightness": 0.1,
                "confidence": 0.2,
                "observed_text": "",
                "reason": "missed",
            },
            {
                "contains_text": True,
                "fully_inside_box": True,
                "matches_hint": True,
                "tightness": 0.9,
                "confidence": 0.95,
                "observed_text": "target",
                "reason": "good",
            },
        ]

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_detection_run",
                return_value="run-test-3",
            ),
            patch(
                "core.usecases.box_detection.missing_react.replace_boxes_for_type",
                side_effect=_replace_boxes_for_type,
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "target",
                        "reason": "missing text",
                        "x": 10.0,
                        "y": 10.0,
                        "width": 30.0,
                        "height": 20.0,
                    }
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                side_effect=verify_results,
            ),
            patch(
                "core.usecases.box_detection.missing_react._adjust_candidate_box",
                return_value={
                    "x": 40.0,
                    "y": 50.0,
                    "width": 25.0,
                    "height": 18.0,
                    "reason": "move to text",
                },
            ) as adjust_mock,
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=1,
                max_attempts_per_candidate=2,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(len(persisted_boxes), 1)
        self.assertEqual(adjust_mock.call_count, 1)
        self.assertAlmostEqual(float(persisted_boxes[0]["x"]), 40.0, places=3)
        self.assertAlmostEqual(float(persisted_boxes[0]["y"]), 50.0, places=3)

    def test_accepts_last_validated_box_when_extra_shrink_loses_text(self) -> None:
        source_image = Image.new("RGB", (200, 200), color="white")
        persisted_boxes: list[dict[str, Any]] = []

        def _replace_boxes_for_type(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            nonlocal persisted_boxes
            payload_boxes = [dict(item) for item in list(kwargs.get("boxes") or [])]
            persisted_boxes = payload_boxes
            return [{"id": idx + 1, **item} for idx, item in enumerate(payload_boxes)]

        verify_results = [
            {
                "contains_text": True,
                "fully_inside_box": True,
                "confidence": 0.95,
                "observed_text": "target",
                "reason": "good",
            },
            {
                "contains_text": True,
                "fully_inside_box": False,
                "text_cut_off": True,
                "confidence": 0.94,
                "observed_text": "target",
                "reason": "clipped",
            },
        ]

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_detection_run",
                return_value="run-test-3b",
            ),
            patch(
                "core.usecases.box_detection.missing_react.replace_boxes_for_type",
                side_effect=_replace_boxes_for_type,
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "target",
                        "reason": "missing text",
                        "x": 20.0,
                        "y": 20.0,
                        "width": 40.0,
                        "height": 30.0,
                    }
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                side_effect=verify_results,
            ),
            patch(
                "core.usecases.box_detection.missing_react._adjust_candidate_box",
                return_value={
                    "x": 24.0,
                    "y": 22.0,
                    "width": 28.0,
                    "height": 22.0,
                    "reason": "shrink more",
                },
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=1,
                max_attempts_per_candidate=2,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(len(persisted_boxes), 1)
        self.assertAlmostEqual(float(persisted_boxes[0]["x"]), 20.0, places=3)
        self.assertAlmostEqual(float(persisted_boxes[0]["y"]), 20.0, places=3)
        self.assertAlmostEqual(float(persisted_boxes[0]["width"]), 40.0, places=3)
        self.assertAlmostEqual(float(persisted_boxes[0]["height"]), 30.0, places=3)

    def test_persists_immediately_after_each_accepted_candidate(self) -> None:
        source_image = Image.new("RGB", (200, 200), color="white")
        persist_calls: list[list[dict[str, Any]]] = []

        def _replace_boxes_for_type(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            boxes = [dict(item) for item in list(kwargs.get("boxes") or [])]
            persist_calls.append(boxes)
            return [{"id": len(persist_calls), **item} for item in boxes]

        verify_outcomes = [
            {
                "contains_text": True,
                "fully_inside_box": True,
                "matches_hint": True,
                "tightness": 0.9,
                "confidence": 0.95,
                "observed_text": "AA",
                "reason": "ok",
            },
            {
                "contains_text": True,
                "fully_inside_box": True,
                "matches_hint": True,
                "tightness": 0.9,
                "confidence": 0.96,
                "observed_text": "BB",
                "reason": "ok",
            },
        ]

        with (
            patch(
                "core.usecases.box_detection.missing_react.has_openai_sdk",
                return_value=True,
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_openai_client",
                return_value=object(),
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_page",
                return_value={"boxes": []},
            ),
            patch(
                "core.usecases.box_detection.missing_react.load_volume_image",
                return_value=source_image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.resize_for_llm",
                side_effect=lambda image, **_: image,
            ),
            patch(
                "core.usecases.box_detection.missing_react.encode_image_data_url",
                return_value="data:image/jpeg;base64,stub",
            ),
            patch(
                "core.usecases.box_detection.missing_react.create_detection_run",
                return_value="run-test-4",
            ) as create_run_mock,
            patch(
                "core.usecases.box_detection.missing_react.replace_boxes_for_type",
                side_effect=_replace_boxes_for_type,
            ),
            patch(
                "core.usecases.box_detection.missing_react._propose_missing_candidates",
                return_value=[
                    {
                        "hint_text": "A",
                        "reason": "missing text",
                        "x": 10.0,
                        "y": 10.0,
                        "width": 20.0,
                        "height": 20.0,
                    },
                    {
                        "hint_text": "B",
                        "reason": "missing text",
                        "x": 60.0,
                        "y": 10.0,
                        "width": 20.0,
                        "height": 20.0,
                    },
                ],
            ),
            patch(
                "core.usecases.box_detection.missing_react._verify_candidate_crop",
                side_effect=verify_outcomes,
            ),
        ):
            result = detect_missing_text_boxes_react(
                volume_id="vol-a",
                filename="001.jpg",
                max_candidates=2,
                max_attempts_per_candidate=1,
                min_confidence=0.7,
            )

        self.assertEqual(result["accepted_count"], 2)
        self.assertEqual(result["created_count"], 2)
        self.assertEqual(create_run_mock.call_count, 1)
        self.assertEqual(len(persist_calls), 2)
        self.assertEqual(len(persist_calls[0]), 1)
        self.assertEqual(len(persist_calls[1]), 1)


if __name__ == "__main__":
    unittest.main()
