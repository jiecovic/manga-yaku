# backend-python/tests/infra/logging/test_artifacts.py
"""Unit tests for shared artifact logging helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from infra.logging import artifacts


def test_write_json_artifact_uses_llm_calls_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        with patch.object(artifacts, "DEBUG_LOGS_DIR", root):
            path = artifacts.write_json_artifact(
                directory=artifacts.llm_calls_dir(),
                filename="abc-123.json",
                payload={"ok": True, "count": 2},
            )

        assert path == root / "llm_calls" / "abc-123.json"
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True, "count": 2}


def test_timestamped_agent_debug_artifact_name_is_safe() -> None:
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

        assert path.name.startswith("agent_debug_run_01_")
        assert path.suffix == ".json"
        assert path.parent == root / "agent" / "translate_page"
        assert json.loads(path.read_text(encoding="utf-8")) == {"volume_id": "Akuhamu"}
