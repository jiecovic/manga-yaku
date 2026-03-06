# backend-python/tests/infra/logging/test_artifacts.py
"""Unit tests for shared artifact logging helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from infra.logging import artifacts


class ArtifactLoggingTests(unittest.TestCase):
    def test_write_json_artifact_uses_llm_calls_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with patch.object(artifacts, "DEBUG_LOGS_DIR", root):
                path = artifacts.write_json_artifact(
                    directory=artifacts.llm_calls_dir(),
                    filename="abc-123.json",
                    payload={"ok": True, "count": 2},
                )

            self.assertEqual(path, root / "llm_calls" / "abc-123.json")
            self.assertTrue(path.is_file())
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"ok": True, "count": 2},
            )

    def test_timestamped_agent_debug_artifact_name_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            with patch.object(artifacts, "DEBUG_LOGS_DIR", root):
                filename = artifacts.timestamped_artifact_name(
                    prefix="agent debug/run 01",
                )
                path = artifacts.write_json_artifact(
                    directory=artifacts.agent_debug_dir("translate_page"),
                    filename=filename,
                    payload={"volume_id": "Akuhamu"},
                )

            self.assertTrue(path.name.startswith("agent_debug_run_01_"))
            self.assertEqual(path.suffix, ".json")
            self.assertEqual(path.parent, root / "agent" / "translate_page")
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                {"volume_id": "Akuhamu"},
            )
