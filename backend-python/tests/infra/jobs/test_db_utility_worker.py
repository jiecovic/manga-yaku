# backend-python/tests/infra/jobs/test_db_utility_worker.py
"""Unit tests for the persisted utility workflow worker."""

from __future__ import annotations

import asyncio
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

from infra.jobs import db_utility_worker
from infra.jobs.exceptions import JobCanceled
from infra.jobs.handlers.training import TrainModelJobHandler
from infra.jobs.store import JobStore


class _FakeHandler:
    async def run(self, job, store):
        store.update_job(job, progress=55, message="Working")
        return {"count": 4}


class _CancelingHandler:
    async def run(self, job, store):
        raise JobCanceled("Canceled")


class _FakeTrainer:
    def __init__(self, *, epochs: int, batches: int) -> None:
        self.epochs = epochs
        self.epoch = 0
        self.train_loader = [object()] * batches
        self.device = "cpu"
        self.optimizer = None
        self.metrics = None
        self.validator = None
        self.args = None
        self.loss_items = None
        self.loss_names = None
        self.gpu_mem = None
        self.stop = False


class _CancelableFakeYOLO:
    instances: ClassVar[list[_CancelableFakeYOLO]] = []

    def __init__(self, model_source: str) -> None:
        self.model_source = model_source
        self.callbacks: dict[str, list[object]] = {}
        self.processed_batches = 0
        self.requested_batches = 0
        _CancelableFakeYOLO.instances.append(self)

    def add_callback(self, name: str, callback: object) -> None:
        self.callbacks.setdefault(name, []).append(callback)

    def _emit(self, name: str, trainer: _FakeTrainer) -> None:
        for callback in self.callbacks.get(name, []):
            callback(trainer)

    def train(self, **kwargs) -> None:
        epochs = int(kwargs.get("epochs") or 1)
        trainer = _FakeTrainer(epochs=epochs, batches=4)
        self.requested_batches = trainer.epochs * len(trainer.train_loader)
        self._emit("on_train_start", trainer)
        for epoch_index in range(trainer.epochs):
            trainer.epoch = epoch_index
            self._emit("on_train_epoch_start", trainer)
            for _ in trainer.train_loader:
                if trainer.stop:
                    break
                self.processed_batches += 1
                self._emit("on_train_batch_end", trainer)
            if trainer.stop:
                break
            self._emit("on_train_epoch_end", trainer)
        if not trainer.stop:
            self._emit("on_train_end", trainer)


class UtilityDbWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_claimed_task_persists_progress_and_terminal_result(self) -> None:
        signal_store = JobStore()
        claimed = {
            "workflow_id": "wf-box-1",
            "task_id": "task-box-1",
            "workflow_type": "box_detection",
            "payload": {"volumeId": "vol-a", "filename": "001.jpg"},
        }
        run_record = {
            "id": "wf-box-1",
            "workflow_type": "box_detection",
            "volume_id": "vol-a",
            "filename": "001.jpg",
            "status": "running",
            "cancel_requested": False,
            "created_at": None,
            "updated_at": None,
            "result_json": {
                "request": {"volumeId": "vol-a", "filename": "001.jpg"},
                "progress": 0,
                "message": "Queued",
            },
        }

        with (
            patch.object(
                db_utility_worker,
                "HANDLERS",
                {"box_detection": _FakeHandler()},
            ),
            patch.object(
                db_utility_worker,
                "get_workflow_run",
                return_value=run_record,
            ),
            patch.object(db_utility_worker, "update_task_run") as update_task_mock,
            patch.object(db_utility_worker, "update_workflow_run") as update_workflow_mock,
        ):
            await db_utility_worker._run_claimed_task(
                claimed,
                log_store={},
                shutdown_event=threading.Event(),
                signal_store=signal_store,
            )

        self.assertGreaterEqual(update_task_mock.call_count, 2)
        self.assertGreaterEqual(update_workflow_mock.call_count, 2)
        final_task_call = update_task_mock.call_args_list[-1]
        self.assertEqual(final_task_call.kwargs["status"], "completed")
        self.assertEqual(final_task_call.kwargs["result_json"]["count"], 4)

        final_workflow_call = update_workflow_mock.call_args_list[-1]
        self.assertEqual(final_workflow_call.kwargs["status"], "completed")
        self.assertEqual(final_workflow_call.kwargs["result_json"]["request"]["volumeId"], "vol-a")
        self.assertEqual(final_workflow_call.kwargs["result_json"]["count"], 4)

    async def test_run_claimed_task_marks_canceled_when_handler_raises_job_canceled(self) -> None:
        signal_store = JobStore()
        claimed = {
            "workflow_id": "wf-train-1",
            "task_id": "task-train-1",
            "workflow_type": "train_model",
            "payload": {"dataset_id": "dataset-1"},
        }
        run_record = {
            "id": "wf-train-1",
            "workflow_type": "train_model",
            "volume_id": "",
            "filename": "",
            "status": "running",
            "cancel_requested": False,
            "created_at": None,
            "updated_at": None,
            "result_json": {
                "request": {"dataset_id": "dataset-1"},
                "progress": 0,
                "message": "Queued",
            },
        }

        with (
            patch.object(
                db_utility_worker,
                "HANDLERS",
                {"train_model": _CancelingHandler()},
            ),
            patch.object(
                db_utility_worker,
                "get_workflow_run",
                return_value=run_record,
            ),
            patch.object(db_utility_worker, "update_task_run") as update_task_mock,
            patch.object(db_utility_worker, "update_workflow_run") as update_workflow_mock,
        ):
            await db_utility_worker._run_claimed_task(
                claimed,
                log_store={},
                shutdown_event=threading.Event(),
                signal_store=signal_store,
            )

        self.assertEqual(update_task_mock.call_args_list[-1].kwargs["status"], "canceled")
        self.assertEqual(update_workflow_mock.call_args_list[-1].kwargs["status"], "canceled")


class UtilityTrainingCancelIntegrationTests(unittest.TestCase):
    def test_persisted_train_model_cancel_stops_training_run(self) -> None:
        _CancelableFakeYOLO.instances.clear()
        signal_store = JobStore()
        claimed = {
            "workflow_id": "wf-train-live-1",
            "task_id": "task-train-live-1",
            "workflow_type": "train_model",
            "payload": {"dataset_id": "dataset-1", "epochs": 3},
        }
        run_record = {
            "id": "wf-train-live-1",
            "workflow_type": "train_model",
            "volume_id": "",
            "filename": "",
            "status": "running",
            "cancel_requested": False,
            "created_at": None,
            "updated_at": None,
            "result_json": {
                "request": {"dataset_id": "dataset-1", "epochs": 3},
                "progress": 0,
                "message": "Queued",
            },
        }

        def get_workflow_run_side_effect(_workflow_id: str) -> dict[str, object]:
            current = dict(run_record)
            current["cancel_requested"] = bool(
                _CancelableFakeYOLO.instances
                and _CancelableFakeYOLO.instances[-1].processed_batches >= 2
            )
            return current

        fake_ultralytics = types.ModuleType("ultralytics")
        fake_ultralytics.YOLO = _CancelableFakeYOLO

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            dataset_dir = root / "dataset-1"
            dataset_dir.mkdir(parents=True, exist_ok=True)
            (dataset_dir / "data.yaml").write_text(
                "path: .\ntrain: images/train\nval: images/val\nnames:\n  0: text\n",
                encoding="utf-8",
            )
            runs_root = root / "runs"
            weights_root = root / "weights"
            runs_root.mkdir(parents=True, exist_ok=True)
            weights_root.mkdir(parents=True, exist_ok=True)

            async def _run_sync(func, /, *args, **kwargs):
                return func(*args, **kwargs)

            with (
                patch.dict(sys.modules, {"ultralytics": fake_ultralytics}),
                patch.object(
                    db_utility_worker,
                    "HANDLERS",
                    {"train_model": TrainModelJobHandler()},
                ),
                patch("infra.jobs.handlers.training.asyncio.to_thread", side_effect=_run_sync),
                patch.object(
                    db_utility_worker,
                    "get_workflow_run",
                    side_effect=get_workflow_run_side_effect,
                ),
                patch.object(db_utility_worker, "update_task_run") as update_task_mock,
                patch.object(db_utility_worker, "update_workflow_run") as update_workflow_mock,
                patch(
                    "infra.training.job_runner.resolve_prepared_dataset",
                    return_value=dataset_dir,
                ),
                patch("infra.training.job_runner.configure_ultralytics_settings"),
                patch("infra.training.job_runner.TRAINING_RUNS_ROOT", runs_root),
                patch("infra.training.job_runner.ULTRALYTICS_WEIGHTS_ROOT", weights_root),
            ):
                asyncio.run(
                    db_utility_worker._run_claimed_task(
                        claimed,
                        log_store={},
                        shutdown_event=threading.Event(),
                        signal_store=signal_store,
                    )
                )

        fake_model = _CancelableFakeYOLO.instances[-1]
        self.assertGreaterEqual(fake_model.processed_batches, 2)
        self.assertLess(fake_model.processed_batches, fake_model.requested_batches)
        self.assertEqual(update_task_mock.call_args_list[-1].kwargs["status"], "canceled")
        self.assertEqual(
            update_task_mock.call_args_list[-1].kwargs["error_code"],
            "cancel_requested",
        )
        self.assertEqual(update_workflow_mock.call_args_list[-1].kwargs["status"], "canceled")
