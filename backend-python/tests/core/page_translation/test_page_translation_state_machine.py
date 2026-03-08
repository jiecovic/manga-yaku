# backend-python/tests/core/page_translation/test_page_translation_state_machine.py
"""Unit tests for the page-translation workflow state machine contract.

What is tested:
- Allowed transitions across the happy path and cancellation paths.
- Terminal-state detection for completed/failed/canceled states.
- Rejection of invalid transition events.

How it is tested:
- Deterministic enum transitions with direct calls to transition helpers.
- No async runtime, DB, or HTTP layers involved.
"""

from __future__ import annotations

import pytest
from core.workflows.page_translation.state.state_machine import (
    is_terminal,
    transition,
)
from core.workflows.page_translation.state.types import WorkflowEvent, WorkflowState


def test_happy_path_transitions() -> None:
    state = WorkflowState.queued
    state = transition(state, WorkflowEvent.start_requested)
    assert state == WorkflowState.detecting_boxes

    state = transition(state, WorkflowEvent.detect_succeeded)
    assert state == WorkflowState.ocr_running

    state = transition(state, WorkflowEvent.ocr_succeeded)
    assert state == WorkflowState.translating

    state = transition(state, WorkflowEvent.translate_succeeded)
    assert state == WorkflowState.committing

    state = transition(state, WorkflowEvent.commit_succeeded)
    assert state == WorkflowState.completed


def test_invalid_transition_raises() -> None:
    with pytest.raises(ValueError):
        transition(WorkflowState.completed, WorkflowEvent.commit_succeeded)


def test_terminal_state_check() -> None:
    assert is_terminal(WorkflowState.completed)
    assert is_terminal(WorkflowState.failed)
    assert is_terminal(WorkflowState.canceled)
    assert not is_terminal(WorkflowState.translating)
