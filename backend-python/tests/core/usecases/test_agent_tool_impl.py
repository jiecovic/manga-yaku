# backend-python/tests/core/usecases/test_agent_tool_impl.py
"""Tests for agent tool helper defaults and workflow wiring."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from core.usecases.agent.tool_impl import (
    list_text_boxes_tool,
    ocr_text_box_tool,
    update_text_box_fields_tool,
)


class AgentToolHelpersTests(unittest.TestCase):
    def test_list_text_boxes_defaults_to_active_page(self) -> None:
        with patch(
            "core.usecases.agent.tool_boxes.load_page",
            return_value={
                "boxes": [
                    {
                        "id": 1,
                        "type": "text",
                        "orderIndex": 1,
                        "x": 10,
                        "y": 20,
                        "width": 30,
                        "height": 40,
                        "text": "jp",
                        "translation": "en",
                        "note": "n",
                    }
                ]
            },
        ) as load_page_mock:
            result = list_text_boxes_tool(
                volume_id="vol-a",
                active_filename="001.jpg",
                filename=None,
                limit=10,
            )

        self.assertEqual(result["filename"], "001.jpg")
        self.assertEqual(result["total"], 1)
        load_page_mock.assert_called_once_with("vol-a", "001.jpg")

    def test_update_text_box_fields_defaults_to_active_page(self) -> None:
        initial_page = {
            "boxes": [
                {
                    "id": 7,
                    "type": "text",
                    "orderIndex": 7,
                    "x": 1,
                    "y": 2,
                    "width": 3,
                    "height": 4,
                    "text": "old",
                    "translation": "",
                    "note": "",
                }
            ]
        }
        updated_page = {
            "boxes": [
                {
                    "id": 7,
                    "type": "text",
                    "orderIndex": 7,
                    "x": 1,
                    "y": 2,
                    "width": 3,
                    "height": 4,
                    "text": "old",
                    "translation": "",
                    "note": "checked",
                }
            ]
        }
        with (
            patch(
                "core.usecases.agent.tool_boxes.load_page",
                side_effect=[initial_page, updated_page],
            ) as load_page_mock,
            patch("core.usecases.agent.tool_boxes.set_box_note_by_id") as set_note_mock,
            patch(
                "core.usecases.agent.tool_boxes.get_active_page_revision",
                return_value="rev-1",
            ),
        ):
            result = update_text_box_fields_tool(
                volume_id="vol-a",
                active_filename="001.jpg",
                box_id=7,
                filename=None,
                note="checked",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["filename"], "001.jpg")
        set_note_mock.assert_called_once_with("vol-a", "001.jpg", box_id=7, note="checked")
        self.assertEqual(load_page_mock.call_count, 2)

    def test_ocr_text_box_defaults_to_active_page(self) -> None:
        page = {
            "boxes": [
                {
                    "id": 5,
                    "type": "text",
                    "orderIndex": 2,
                    "x": 10,
                    "y": 20,
                    "width": 30,
                    "height": 40,
                    "text": "ocr text",
                    "translation": "",
                    "note": "",
                }
            ]
        }
        with (
            patch(
                "core.usecases.agent.tool_jobs.load_page",
                side_effect=[page, page],
            ) as load_page_mock,
            patch(
                "core.usecases.agent.tool_jobs.create_ocr_box_workflow",
                return_value="wf-123",
            ) as create_workflow_mock,
            patch(
                "core.usecases.agent.tool_jobs.wait_for_workflow_terminal",
                return_value={
                    "status": "completed",
                    "result_json": {"message": "done"},
                },
            ),
            patch(
                "core.usecases.agent.tool_jobs.get_active_page_revision",
                return_value="rev-2",
            ),
        ):
            result = ocr_text_box_tool(
                volume_id="vol-a",
                active_filename="001.jpg",
                box_id=5,
                filename=None,
                profile_id="manga_ocr_default",
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["filename"], "001.jpg")
        create_workflow_mock.assert_called_once()
        workflow_input = create_workflow_mock.call_args.args[0]
        self.assertEqual(workflow_input.filename, "001.jpg")
        self.assertEqual(workflow_input.box_id, 5)
        self.assertEqual(load_page_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
