# backend-python/tests/core/usecases/test_agent_prompt_defaults.py
"""Tests for shared agent translation language defaults."""

from __future__ import annotations

import unittest

from config import TRANSLATION_SOURCE_LANGUAGE, TRANSLATION_TARGET_LANGUAGE
from core.usecases.agent.engine import _load_system_prompt
from core.workflows.agent_translate_page.types import AgentTranslatePageRequest


class AgentPromptDefaultsTests(unittest.TestCase):
    def test_load_system_prompt_renders_shared_language_defaults(self) -> None:
        prompt = _load_system_prompt()

        self.assertIn(TRANSLATION_SOURCE_LANGUAGE, prompt)
        self.assertIn(TRANSLATION_TARGET_LANGUAGE, prompt)
        self.assertNotIn("{{SOURCE_LANG}}", prompt)
        self.assertNotIn("{{TARGET_LANG}}", prompt)

    def test_agent_translate_request_uses_shared_language_defaults(self) -> None:
        request = AgentTranslatePageRequest.from_payload(
            {
                "volumeId": "vol-a",
                "filename": "001.jpg",
            }
        )

        self.assertEqual(request.source_language, TRANSLATION_SOURCE_LANGUAGE)
        self.assertEqual(request.target_language, TRANSLATION_TARGET_LANGUAGE)


if __name__ == "__main__":
    unittest.main()
