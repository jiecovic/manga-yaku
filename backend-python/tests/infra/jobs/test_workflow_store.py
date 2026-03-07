"""Pytest coverage for workflow store restart interruption helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from unittest.mock import patch

from infra.db import workflow_store


@dataclass
class _FakeWorkflowRow:
    workflow_type: str
    status: str
    state: str
    error_message: str | None = None
    updated_at: datetime | None = None


class _FakeScalarResult:
    def __init__(self, rows: list[_FakeWorkflowRow]) -> None:
        self._rows = rows

    def all(self) -> list[_FakeWorkflowRow]:
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows: list[_FakeWorkflowRow]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalarResult:
        return _FakeScalarResult(self._rows)


class _FakeSession:
    def __init__(self, rows: list[_FakeWorkflowRow]) -> None:
        self._rows = rows

    def execute(self, _stmt: Any) -> _FakeExecuteResult:
        filtered = [
            row for row in self._rows if row.status == "running"
        ]
        return _FakeExecuteResult(filtered)


@contextmanager
def _fake_session_scope(rows: list[_FakeWorkflowRow]):
    yield _FakeSession(rows)


def test_mark_running_workflows_interrupted_leaves_queued_runs_untouched_by_default() -> None:
    queued = _FakeWorkflowRow(
        workflow_type="agent_translate_page",
        status="queued",
        state="queued",
    )
    running = _FakeWorkflowRow(
        workflow_type="agent_translate_page",
        status="running",
        state="running",
    )

    with patch(
        "infra.db.workflow_store.get_session",
        side_effect=lambda: _fake_session_scope([queued, running]),
    ):
        changed = workflow_store.mark_running_workflows_interrupted(
            workflow_type="agent_translate_page",
        )

    assert changed == 1
    assert queued.status == "queued"
    assert queued.state == "queued"
    assert queued.error_message is None
    assert queued.updated_at is None
    assert running.status == "failed"
    assert running.state == "failed"
    assert running.error_message == "Interrupted by backend restart"
    assert running.updated_at is not None


class _FilteringSession(_FakeSession):
    def execute(self, _stmt: Any) -> _FakeExecuteResult:
        return _FakeExecuteResult(list(self._rows))


@contextmanager
def _filtering_session_scope(rows: list[_FakeWorkflowRow]):
    yield _FilteringSession(rows)


def test_mark_running_workflows_interrupted_can_include_queued_runs() -> None:
    queued = _FakeWorkflowRow(
        workflow_type="agent_translate_page",
        status="queued",
        state="queued",
    )
    running = _FakeWorkflowRow(
        workflow_type="agent_translate_page",
        status="running",
        state="running",
    )

    with patch(
        "infra.db.workflow_store.get_session",
        side_effect=lambda: _filtering_session_scope([queued, running]),
    ):
        changed = workflow_store.mark_running_workflows_interrupted(
            workflow_type="agent_translate_page",
            include_queued=True,
        )

    assert changed == 2
    assert queued.status == "failed"
    assert queued.state == "failed"
    assert queued.error_message == "Interrupted by backend restart"
    assert queued.updated_at is not None
    assert running.status == "failed"
    assert running.state == "failed"
    assert running.error_message == "Interrupted by backend restart"
    assert running.updated_at is not None
