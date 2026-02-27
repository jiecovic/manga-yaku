"""Unit tests for agent workflow state transitions and terminal checks.

These tests assert allowed transition paths and confirm invalid transitions
raise errors.
"""

from __future__ import annotations

import unittest

from core.workflows.agent_translate_page.state_machine import is_terminal, transition
from core.workflows.agent_translate_page.types import WorkflowEvent, WorkflowState


class AgentStateMachineTests(unittest.TestCase):
    def test_happy_path_transitions(self) -> None:
        state = WorkflowState.queued
        state = transition(state, WorkflowEvent.start_requested)
        self.assertEqual(state, WorkflowState.detecting_boxes)

        state = transition(state, WorkflowEvent.detect_succeeded)
        self.assertEqual(state, WorkflowState.ocr_running)

        state = transition(state, WorkflowEvent.ocr_succeeded)
        self.assertEqual(state, WorkflowState.translating)

        state = transition(state, WorkflowEvent.translate_succeeded)
        self.assertEqual(state, WorkflowState.committing)

        state = transition(state, WorkflowEvent.commit_succeeded)
        self.assertEqual(state, WorkflowState.completed)

    def test_invalid_transition_raises(self) -> None:
        with self.assertRaises(ValueError):
            transition(WorkflowState.completed, WorkflowEvent.commit_succeeded)

    def test_terminal_state_check(self) -> None:
        self.assertTrue(is_terminal(WorkflowState.completed))
        self.assertTrue(is_terminal(WorkflowState.failed))
        self.assertTrue(is_terminal(WorkflowState.canceled))
        self.assertFalse(is_terminal(WorkflowState.translating))
