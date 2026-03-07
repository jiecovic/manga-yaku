# backend-python/tests/core/usecases/test_agent_prompt_defaults.py
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

    def test_load_system_prompt_mentions_page_memory_tools_and_verification(self) -> None:
        prompt = _load_system_prompt()

        self.assertIn("get_page_memory", prompt)
        self.assertIn("update_page_memory", prompt)
        self.assertIn("verify saved results", prompt)
        self.assertIn("prefer translate_active_page", prompt)
        self.assertIn("use primitive tools only if you need follow-up inspection", prompt)
        self.assertIn("If all current boxes already have translations", prompt)
        self.assertIn("Do not describe the page as translated yet", prompt)
        self.assertIn("Only claim the page was already translated if translate_active_page returns status=already_translated", prompt)
        self.assertIn("force_rerun=true", prompt)
        self.assertIn("do not ask the user to upload/share another screenshot", prompt)
        self.assertIn("If a visual check is still needed, inspect one box crop at a time", prompt)
        self.assertIn("do not call view_text_box", prompt.lower())
        self.assertIn("Avoid requesting multiple box-image crops in parallel", prompt)
        self.assertNotIn("detect_missing_boxes", prompt)
        self.assertIn("detection likely missed text", prompt)
        self.assertIn("run the page-translation workflow", prompt)


if __name__ == "__main__":
    unittest.main()
