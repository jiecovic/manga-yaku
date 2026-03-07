# backend-python/tests/infra/jobs/test_workflow_repo_recovery.py
"""Pytest coverage for workflow-repo restart recovery semantics."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from infra.jobs import workflow_repo


@dataclass
class _FakeTaskRow:
    status: str = "running"
    finished_at: datetime | None = None
    error_code: str | None = None
    error_detail: str | None = None
    lease_until: Any = field(default_factory=object)
    updated_at: datetime | None = None


@dataclass
class _FakeWorkflowRow:
    status: str = "running"
    state: str = "running"
    cancel_requested: bool = False
    updated_at: datetime | None = None


class _FakeResult:
    def __init__(self, rows: list[tuple[_FakeTaskRow, _FakeWorkflowRow]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[_FakeTaskRow, _FakeWorkflowRow]]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows: list[tuple[_FakeTaskRow, _FakeWorkflowRow]]) -> None:
        self._rows = rows

    def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self._rows)


@contextmanager
def _fake_session_scope(rows: list[tuple[_FakeTaskRow, _FakeWorkflowRow]]):
    yield _FakeSession(rows)


def test_recover_running_tasks_requeues_interrupted_work_on_startup() -> None:
    task_row = _FakeTaskRow()
    workflow_row = _FakeWorkflowRow(cancel_requested=False)

    with patch(
        "infra.jobs.workflow_repo.get_session",
        side_effect=lambda: _fake_session_scope([(task_row, workflow_row)]),
    ):
        changed = workflow_repo.recover_running_tasks_for_startup(
            workflow_types=("train_model",),
            stage="train_model",
        )

    assert changed == 1
    assert task_row.status == "queued"
    assert task_row.error_code == "worker_restart"
    assert task_row.error_detail == "Requeued after backend restart"
    assert task_row.lease_until is None
    assert isinstance(task_row.updated_at, datetime)
    assert workflow_row.status == "queued"
    assert workflow_row.state == "queued"
    assert isinstance(workflow_row.updated_at, datetime)


def test_recover_running_tasks_keeps_canceled_work_canceled() -> None:
    task_row = _FakeTaskRow()
    workflow_row = _FakeWorkflowRow(
        status="canceled",
        state="running",
        cancel_requested=True,
    )

    with patch(
        "infra.jobs.workflow_repo.get_session",
        side_effect=lambda: _fake_session_scope([(task_row, workflow_row)]),
    ):
        changed = workflow_repo.recover_running_tasks_for_startup(
            workflow_types=("prepare_dataset",),
            stage="prepare_dataset",
        )

    assert changed == 1
    assert task_row.status == "canceled"
    assert task_row.error_code == "cancel_requested"
    assert task_row.error_detail == "Canceled"
    assert task_row.lease_until is None
    assert isinstance(task_row.finished_at, datetime)
    assert task_row.finished_at.tzinfo == timezone.utc
    assert workflow_row.status == "canceled"
    assert workflow_row.state == "canceled"
    assert isinstance(workflow_row.updated_at, datetime)
