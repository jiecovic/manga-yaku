# backend-python/tests/infra/jobs/test_job_handler_cancellation.py
"""Regression tests for cooperative cancel hooks in utility job handlers."""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from infra.jobs.handlers.training import PrepareDatasetJobHandler, TrainModelJobHandler
from infra.jobs.store import Job, JobStatus


class _FakeStore:
    def __init__(self) -> None:
        self.logs: dict[str, Path] = {}
        self.shutdown_event = threading.Event()
        self.update_calls: list[dict[str, object]] = []

    def update_job(self, job: Job, **updates: object) -> Job:
        for key, value in updates.items():
            setattr(job, key, value)
        self.update_calls.append(dict(updates))
        return job

    def is_canceled(self) -> bool:
        return False


def _job(*, job_type: str, payload: dict[str, object]) -> Job:
    return Job(
        id=f"job-{job_type}",
        type=job_type,
        status=JobStatus.queued,
        created_at=0.0,
        updated_at=0.0,
        payload=payload,
    )


class JobHandlerCancelationTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_dataset_handler_passes_cancel_hook(self) -> None:
        handler = PrepareDatasetJobHandler()
        store = _FakeStore()

        async def _run_sync(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("infra.jobs.handlers.training.asyncio.to_thread", side_effect=_run_sync),
            patch(
                "infra.jobs.handlers.training.resolve_training_sources",
                return_value=[Path("/tmp/source")],
            ),
            patch(
                "infra.jobs.handlers.training.prepare_dataset",
                return_value=(
                    "dataset-1",
                    Path("/tmp/out"),
                    SimpleNamespace(
                        train_images=1,
                        val_images=2,
                        train_labels=3,
                        val_labels=4,
                    ),
                ),
            ) as prepare_mock,
        ):
            result = await handler.run(
                _job(
                    job_type="prepare_dataset",
                    payload={"sources": ["manga109s:demo"]},
                ),
                store,  # type: ignore[arg-type]
            )

        self.assertEqual(result["dataset_id"], "dataset-1")
        cancel_cb = prepare_mock.call_args.kwargs["is_canceled"]
        self.assertTrue(callable(cancel_cb))
        self.assertFalse(cancel_cb())

    async def test_train_model_handler_passes_cancel_hook(self) -> None:
        handler = TrainModelJobHandler()
        store = _FakeStore()

        async def _run_sync(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        with (
            patch("infra.jobs.handlers.training.asyncio.to_thread", side_effect=_run_sync),
            patch(
                "infra.jobs.handlers.training.run_training_job",
                return_value={"dry_run": True},
            ) as run_mock,
        ):
            result = await handler.run(
                _job(
                    job_type="train_model",
                    payload={"dataset_id": "dataset-1", "dry_run": True},
                ),
                store,  # type: ignore[arg-type]
            )

        self.assertEqual(result["dry_run"], True)
        cancel_cb = run_mock.call_args.kwargs["is_canceled"]
        self.assertTrue(callable(cancel_cb))
        self.assertFalse(cancel_cb())
