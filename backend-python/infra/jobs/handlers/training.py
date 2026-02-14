# backend-python/infra/jobs/handlers/training.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from infra.training.catalog import resolve_training_sources
from infra.training.dataset_builder import prepare_dataset
from infra.training.job_runner import run_training_job

from ..store import Job, JobStatus, JobStore
from .base import JobHandler


class PrepareDatasetResult(TypedDict):
    dataset_id: str
    path: str
    stats: dict[str, int]


class TrainModelResult(TypedDict, total=False):
    run_id: str
    run_dir: str
    weights: dict[str, str]
    log: str | None
    dry_run: bool
    canceled: bool


@dataclass(frozen=True)
class PrepareDatasetInput:
    dataset_id: str | None
    sources: list[str]
    targets: list[str] | None
    val_split: float
    test_split: float
    link_mode: str
    seed: int
    overwrite: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> PrepareDatasetInput:
        return cls(
            dataset_id=payload.get("dataset_id"),
            sources=list(payload.get("sources") or []),
            targets=payload.get("targets"),
            val_split=float(payload.get("val_split", 0.15)),
            test_split=float(payload.get("test_split", 0.0)),
            link_mode=str(payload.get("link_mode", "copy")),
            seed=int(payload.get("seed", 1337)),
            overwrite=bool(payload.get("overwrite", False)),
        )


class PrepareDatasetJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> PrepareDatasetResult:
        data = PrepareDatasetInput.from_payload(dict(job.payload))
        source_dirs = resolve_training_sources(
            data.sources,
            allowed_types={"manga109s"},
        )

        loop = asyncio.get_running_loop()
        last_percent = -1

        def progress_cb(processed: int, total: int, label: str) -> None:
            nonlocal last_percent
            if total <= 0:
                return
            percent = int((processed / total) * 100)
            if percent == last_percent and processed != total:
                return
            last_percent = percent
            message = f"{processed}/{total} {label}"

            def _apply_update(target_job: Job, progress_value: int, message_value: str) -> None:
                store.update_job(target_job, progress=progress_value, message=message_value)

            loop.call_soon_threadsafe(_apply_update, job, percent, message)

        store.update_job(job, progress=0, message="Starting dataset build")

        dataset_id, out_dir, stats = await asyncio.to_thread(
            prepare_dataset,
            dataset_id=data.dataset_id,
            source_dirs=source_dirs,
            targets=data.targets,
            val_split=data.val_split,
            test_split=data.test_split,
            link_mode=data.link_mode,
            seed=data.seed,
            overwrite=data.overwrite,
            progress_cb=progress_cb,
        )

        result: PrepareDatasetResult = {
            "dataset_id": dataset_id,
            "path": str(out_dir),
            "stats": {
                "train_images": int(stats.train_images),
                "val_images": int(stats.val_images),
                "train_labels": int(stats.train_labels),
                "val_labels": int(stats.val_labels),
            },
        }

        store.update_job(job, progress=100, message="Dataset build complete")
        return result


class TrainModelJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> TrainModelResult:
        payload = job.payload
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(
            run_training_job,
            job=job,
            payload=payload,
            loop=loop,
            update_job=store.update_job,
            log_store=store.logs,
            shutdown_event=store.shutdown_event,
            status_canceled=JobStatus.canceled,
        )
