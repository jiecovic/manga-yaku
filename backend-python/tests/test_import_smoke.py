"""Smoke tests for clean module imports in a fresh interpreter.

What this protects:
- Direct importability of modules that previously depended on import order.
- Regressions where package `__init__` files or compatibility facades
  accidentally reintroduce circular imports.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend-python"


class ImportSmokeTests(unittest.TestCase):
    def _assert_imports_clean(self, code: str) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(BACKEND_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=result.stderr or result.stdout or "import smoke test failed",
        )

    def test_jobs_routes_imports_cleanly(self) -> None:
        self._assert_imports_clean(
            "from api.routers.jobs.routes import list_jobs; print(list_jobs.__name__)"
        )

    def test_agent_workflow_state_machine_imports_cleanly(self) -> None:
        self._assert_imports_clean(
            "from core.workflows.agent_translate_page.state_machine import transition; "
            "print(transition.__name__)"
        )

    def test_jobs_runtime_imports_cleanly(self) -> None:
        self._assert_imports_clean(
            "from infra.jobs.runtime import STORE; print(type(STORE).__name__)"
        )
