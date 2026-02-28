"""State machine transitions and guards for the agent translate page workflow."""

from __future__ import annotations

from .types import WorkflowEvent, WorkflowState

_TRANSITIONS: dict[WorkflowState, dict[WorkflowEvent, WorkflowState]] = {
    WorkflowState.queued: {
        WorkflowEvent.start_requested: WorkflowState.detecting_boxes,
        WorkflowEvent.cancel_requested: WorkflowState.canceled,
    },
    WorkflowState.detecting_boxes: {
        WorkflowEvent.detect_succeeded: WorkflowState.ocr_running,
        WorkflowEvent.detect_failed: WorkflowState.failed,
        WorkflowEvent.cancel_requested: WorkflowState.canceled,
    },
    WorkflowState.ocr_running: {
        WorkflowEvent.ocr_succeeded: WorkflowState.translating,
        WorkflowEvent.ocr_failed: WorkflowState.failed,
        WorkflowEvent.cancel_requested: WorkflowState.canceled,
    },
    WorkflowState.translating: {
        WorkflowEvent.translate_succeeded: WorkflowState.committing,
        WorkflowEvent.translate_failed: WorkflowState.failed,
        WorkflowEvent.cancel_requested: WorkflowState.canceled,
    },
    WorkflowState.committing: {
        WorkflowEvent.commit_succeeded: WorkflowState.completed,
        WorkflowEvent.commit_failed: WorkflowState.failed,
    },
    WorkflowState.completed: {},
    WorkflowState.failed: {},
    WorkflowState.canceled: {},
}


def transition(state: WorkflowState, event: WorkflowEvent) -> WorkflowState:
    next_state = _TRANSITIONS.get(state, {}).get(event)
    if next_state is None:
        raise ValueError(f"Invalid transition: {state.value} + {event.value}")
    return next_state


def is_terminal(state: WorkflowState) -> bool:
    return state in {
        WorkflowState.completed,
        WorkflowState.failed,
        WorkflowState.canceled,
    }
