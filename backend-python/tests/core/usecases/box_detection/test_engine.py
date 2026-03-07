"""Pytest coverage for box-detection orchestration behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from core.usecases.box_detection import engine


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
            "_load_page_image",
            return_value=SimpleNamespace(size=(100, 100)),
        ),
        patch.object(engine, "_resolve_allowed_classes", return_value=None),
        patch.object(engine, "_run_yolo_on_image", side_effect=run_yolo_side_effect),
        patch.object(engine, "_resolve_model_path", return_value=None),
        patch.object(engine, "_get_model_hash", return_value=None),
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
