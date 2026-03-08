# backend-python/tests/core/usecases/box_detection/test_engine.py
"""Pytest coverage for box-detection orchestration behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from core.usecases.box_detection.runtime import engine


def test_detect_boxes_for_page_skips_db_writes_after_cancel() -> None:
    cancel_requested = False

    def is_canceled() -> bool:
        return cancel_requested

    def run_yolo_side_effect(*args, **kwargs):
        nonlocal cancel_requested
        cancel_requested = True
        return [
            {
                "x": 10.0,
                "y": 20.0,
                "width": 30.0,
                "height": 40.0,
                "score": 0.95,
            }
        ]

    with (
        patch.object(engine, "pick_default_box_detection_profile_id", return_value="default"),
        patch.object(
            engine,
            "get_box_detection_profile",
            return_value={"id": "default", "enabled": True, "config": {}},
        ),
        patch.object(
            engine,
            "load_page_image",
            return_value=SimpleNamespace(size=(100, 100)),
        ),
        patch.object(engine, "resolve_allowed_classes", return_value=None),
        patch.object(engine, "run_yolo_on_image", side_effect=run_yolo_side_effect),
        patch.object(engine, "resolve_model_path", return_value=None),
        patch.object(engine, "get_model_hash", return_value=None),
        patch.object(engine, "create_detection_run") as create_run_mock,
        patch.object(engine, "replace_boxes_for_type") as replace_mock,
    ):
        result = engine.detect_boxes_for_page(
            "vol-a",
            "001.jpg",
            task="text",
            is_canceled=is_canceled,
        )

    assert result == []
    create_run_mock.assert_not_called()
    replace_mock.assert_not_called()


def test_detect_boxes_for_page_skips_detections_overlapping_existing_boxes() -> None:
    with (
        patch.object(engine, "pick_default_box_detection_profile_id", return_value="default"),
        patch.object(
            engine,
            "get_box_detection_profile",
            return_value={"id": "default", "enabled": True, "config": {}},
        ),
        patch.object(
            engine,
            "load_page_image",
            return_value=SimpleNamespace(size=(100, 100)),
        ),
        patch.object(engine, "resolve_allowed_classes", return_value=None),
        patch.object(engine, "resolve_detection_thresholds", return_value=(0.25, 0.45)),
        patch.object(engine, "resolve_containment_threshold", return_value=0.9),
        patch.object(
            engine,
            "run_yolo_on_image",
            return_value=[
                {"x": 10.0, "y": 10.0, "width": 20.0, "height": 20.0, "score": 0.9},
                {"x": 70.0, "y": 70.0, "width": 10.0, "height": 10.0, "score": 0.8},
            ],
        ),
        patch.object(engine, "resolve_model_path", return_value=None),
        patch.object(engine, "get_model_hash", return_value=None),
        patch.object(engine, "create_detection_run", return_value="run-1"),
        patch.object(
            engine,
            "load_page",
            return_value={
                "boxes": [
                    {
                        "id": 1,
                        "type": "text",
                        "x": 11.0,
                        "y": 11.0,
                        "width": 20.0,
                        "height": 20.0,
                    }
                ]
            },
        ),
        patch.object(
            engine, "replace_boxes_for_type", return_value=[{"box_id": 2}]
        ) as replace_mock,
    ):
        result = engine.detect_boxes_for_page(
            "vol-a",
            "001.jpg",
            task="text",
            replace_existing=False,
        )

    replace_mock.assert_called_once()
    assert replace_mock.call_args.kwargs["boxes"] == [
        {"x": 70.0, "y": 70.0, "width": 10.0, "height": 10.0}
    ]
    assert result == [{"box_id": 2}]
