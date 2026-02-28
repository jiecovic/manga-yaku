# backend-python/infra/training/job_runner.py
"""Training job execution orchestration and process wrappers."""

from __future__ import annotations

import json
import logging
import math
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from config import (
    TRAINING_RUNS_ROOT,
    ULTRALYTICS_WEIGHTS_ROOT,
    configure_ultralytics_settings,
)
from infra.logging.ansi import strip_ansi
from infra.training.catalog import resolve_prepared_dataset


class TrainingCanceled(RuntimeError):
    pass


def next_run_id(project_dir: Path) -> str:
    counter_path = project_dir / "next_run.txt"
    run_number = 1
    if counter_path.exists():
        try:
            raw = counter_path.read_text(encoding="utf-8").strip()
            if raw:
                run_number = int(raw)
        except (OSError, ValueError):
            run_number = 1

    while (project_dir / f"run-{run_number:04d}").exists():
        run_number += 1

    try:
        counter_path.write_text(str(run_number + 1), encoding="utf-8")
    except OSError:
        pass

    return f"run-{run_number:04d}"


def run_training_job(
    *,
    job: Any,
    payload: dict[str, Any],
    loop: Any,
    update_job: Any,
    log_store: dict[str, Path],
    shutdown_event: threading.Event,
    status_canceled: Any,
) -> dict[str, Any]:
    dataset_id = str(payload.get("dataset_id") or "")
    dataset_dir = resolve_prepared_dataset(dataset_id)
    data_yaml = dataset_dir / "data.yaml"
    configure_ultralytics_settings()

    model_family = str(payload.get("model_family") or "yolo26")
    model_size = str(payload.get("model_size") or "n")
    model_id = f"{model_family}{model_size}"
    pretrained = bool(payload.get("pretrained", True))
    epochs = int(payload.get("epochs", 50))
    batch_size = int(payload.get("batch_size", 8))
    workers = int(payload.get("workers", 0))
    image_size = int(payload.get("image_size", 1024))
    device = str(payload.get("device") or "auto").lower()
    patience = int(payload.get("patience", 20))
    augmentations = bool(payload.get("augmentations", True))
    dry_run = bool(payload.get("dry_run", False))

    log_path: Path | None = None
    cleanup_tmp: tempfile.TemporaryDirectory | None = None

    manifest_data: dict | None = None

    if dry_run:
        cleanup_tmp = tempfile.TemporaryDirectory()
        project_dir = Path(cleanup_tmp.name)
    else:
        project_dir = TRAINING_RUNS_ROOT / dataset_id
        project_dir.mkdir(parents=True, exist_ok=True)

    run_id = next_run_id(project_dir)
    run_dir = project_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    log_path = run_dir / "logs.txt"
    log_store[job.id] = log_path

    if not dry_run:
        manifest_data = {
            "run_id": run_id,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_id": dataset_id,
            "data_yaml": str(data_yaml),
            "model": model_id,
            "pretrained": pretrained,
            "epochs": epochs,
            "batch_size": batch_size,
            "workers": workers,
            "image_size": image_size,
            "device": device,
            "patience": patience,
            "augmentations": augmentations,
            "dry_run": dry_run,
            "backend": "python",
        }

    run_name = run_id if not dry_run else "dry-run"
    project_arg = project_dir

    data_yaml_used = data_yaml
    try:
        import yaml

        parsed = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            raw_path = parsed.get("path")
            if isinstance(raw_path, str):
                raw_path_value = Path(raw_path)
                if raw_path.lower().endswith(".yaml") or raw_path_value.suffix.lower() == ".yaml":
                    parsed["path"] = dataset_dir.as_posix()
                    fixed_path = run_dir / "data.yaml"
                    fixed_path.write_text(
                        yaml.safe_dump(parsed, sort_keys=False),
                        encoding="utf-8",
                    )
                    data_yaml_used = fixed_path
    except Exception:
        data_yaml_used = data_yaml

    if dry_run:
        epochs = 1
        batch_size = 1
        image_size = min(image_size, 640)
        workers = 0

    def schedule_update(**updates: Any) -> None:
        loop.call_soon_threadsafe(lambda: update_job(job, **updates))

    schedule_update(message=f"Training {model_id} on {dataset_id}")

    if pretrained:
        model_source = str(ULTRALYTICS_WEIGHTS_ROOT / f"{model_id}.pt")
    else:
        model_source = f"{model_id}.yaml"

    if manifest_data is not None:
        manifest_data["data_yaml_used"] = str(data_yaml_used)
        manifest_data["model_source"] = model_source
        (run_dir / "manifest.json").write_text(
            json.dumps(manifest_data, indent=2),
            encoding="utf-8",
        )

    class _AnsiStripFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            message = record.getMessage()
            if isinstance(message, str):
                record.msg = strip_ansi(message)
                record.args = ()
            return True

    log_handler = logging.FileHandler(log_path, encoding="utf-8")
    log_handler.addFilter(_AnsiStripFilter())
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    yolo_logger = logging.getLogger("ultralytics")
    yolo_logger.addHandler(log_handler)

    state = {
        "last_progress": -1,
        "last_message": "",
        "last_emit": 0.0,
        "epoch": 0,
        "batch": 0,
        "batches": 0,
        "done": False,
        "canceled_logged": False,
    }

    def _to_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        return parsed

    def _set_loss(metrics: dict[str, Any], name: str, value: Any) -> None:
        loss_value = _to_float(value)
        if loss_value is None:
            return
        key = name if name.endswith("loss") else f"{name}_loss"
        metrics[key] = loss_value

    def _get_metric_value(container: Any, key: str) -> Any:
        if container is None:
            return None
        if isinstance(container, dict):
            return container.get(key)
        return getattr(container, key, None)

    def _find_metric(container: Any, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            raw = _get_metric_value(container, key)
            value = _to_float(raw)
            if value is not None:
                return value
        return None

    def _extract_map_metrics(trainer: Any) -> tuple[float | None, float | None]:
        map50_keys = ("map50", "mAP50", "metrics/mAP50(B)", "metrics/mAP50")
        map_keys = ("map", "mAP50-95", "metrics/mAP50-95(B)", "metrics/mAP50-95")

        candidates = []
        metrics = getattr(trainer, "metrics", None)
        if metrics is not None:
            candidates.append(metrics)
            results_dict = _get_metric_value(metrics, "results_dict")
            if results_dict is not None:
                candidates.append(results_dict)

        validator = getattr(trainer, "validator", None)
        validator_metrics = getattr(validator, "metrics", None) if validator is not None else None
        if validator_metrics is not None:
            candidates.append(validator_metrics)
            results_dict = _get_metric_value(validator_metrics, "results_dict")
            if results_dict is not None:
                candidates.append(results_dict)

        map50 = None
        map50_95 = None
        for candidate in candidates:
            if map50 is None:
                map50 = _find_metric(candidate, map50_keys)
            if map50_95 is None:
                map50_95 = _find_metric(candidate, map_keys)

            box = _get_metric_value(candidate, "box")
            if map50 is None:
                map50 = _find_metric(box, ("map50", "mAP50"))
            if map50_95 is None:
                map50_95 = _find_metric(box, ("map", "mAP50-95"))

            if map50 is not None and map50_95 is not None:
                break

        return map50, map50_95

    def build_metrics(trainer: Any) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "epoch": state["epoch"],
            "total_epochs": getattr(trainer, "epochs", None),
            "batch": state["batch"],
            "batches": state["batches"],
        }

        device = getattr(trainer, "device", None)
        if device is None:
            args = getattr(trainer, "args", None)
            if args is not None:
                device = getattr(args, "device", None)
        if device is not None:
            metrics["device"] = str(device)

        gpu_mem = getattr(trainer, "gpu_mem", None)
        if gpu_mem is not None:
            metrics["gpu_mem"] = str(gpu_mem)

        optimizer = getattr(trainer, "optimizer", None)
        if optimizer is not None and getattr(optimizer, "param_groups", None):
            metrics["lr"] = _to_float(optimizer.param_groups[0].get("lr"))

        loss_items = getattr(trainer, "loss_items", None)
        loss_names = getattr(trainer, "loss_names", None)
        if loss_items is None:
            loss_items = getattr(trainer, "tloss", None)
        if loss_items is not None:
            try:
                values = list(loss_items)
            except TypeError:
                values = [loss_items]

            if loss_names:
                for name, value in zip(loss_names, values, strict=False):
                    _set_loss(metrics, str(name), value)
            elif len(values) >= 3:
                for name, value in zip(("box", "cls", "dfl"), values, strict=False):
                    _set_loss(metrics, name, value)

        map50, map50_95 = _extract_map_metrics(trainer)
        if map50 is not None:
            metrics["map50"] = map50
        if map50_95 is not None:
            metrics["map50_95"] = map50_95

        return metrics

    def update_progress(epoch: int, total: int, batch: int, batches: int) -> None:
        if total <= 0:
            return
        if batches <= 0:
            percent = (epoch / total) * 100
        else:
            percent = ((epoch - 1) + (batch / max(batches, 1))) / total * 100
        if not state["done"]:
            percent = min(percent, 99.0)
        message = f"Epoch {epoch}/{total} (batch {batch}/{max(batches, 1)})"
        now = time.monotonic()
        if percent == state["last_progress"] and now - state["last_emit"] < 1.0:
            return
        state["last_progress"] = percent
        state["last_emit"] = now
        if message != state["last_message"]:
            state["last_message"] = message
        schedule_update(progress=percent, message=message)

    def check_canceled(trainer: Any) -> None:
        if job.status != status_canceled and not shutdown_event.is_set():
            return
        trainer.stop = True
        if job.status != status_canceled:
            schedule_update(status=status_canceled, message="Canceled")
        if not state["canceled_logged"]:
            state["canceled_logged"] = True
            yolo_logger.info("Canceled by user.")
        raise TrainingCanceled("Canceled")

    def on_train_start(trainer: Any) -> None:
        state["batches"] = len(trainer.train_loader) if trainer.train_loader is not None else 0
        schedule_update(progress=0, message=f"Training {model_id} on {dataset_id}")
        schedule_update(metrics=build_metrics(trainer))
        yolo_logger.info(f"Training started: {model_id} on {dataset_id}")

    def on_train_epoch_start(trainer: Any) -> None:
        state["epoch"] = trainer.epoch + 1
        state["batch"] = 0
        state["batches"] = len(trainer.train_loader) if trainer.train_loader is not None else 0
        check_canceled(trainer)
        update_progress(state["epoch"], trainer.epochs, state["batch"], state["batches"])
        schedule_update(metrics=build_metrics(trainer))

    def on_train_batch_end(trainer: Any) -> None:
        check_canceled(trainer)
        state["batch"] += 1
        update_progress(state["epoch"], trainer.epochs, state["batch"], state["batches"])
        schedule_update(metrics=build_metrics(trainer))

    def on_train_epoch_end(trainer: Any) -> None:
        check_canceled(trainer)
        yolo_logger.info(f"Epoch {trainer.epoch + 1}/{trainer.epochs} complete")
        schedule_update(metrics=build_metrics(trainer))

    def on_train_end(trainer: Any) -> None:
        state["done"] = True
        if job.status == status_canceled:
            schedule_update(message="Canceled")
            yolo_logger.info("Training canceled")
            return
        schedule_update(progress=100, message="Training complete")
        yolo_logger.info("Training complete")

    try:
        from ultralytics import YOLO

        model = YOLO(model_source)
        model.add_callback("on_train_start", on_train_start)
        model.add_callback("on_train_epoch_start", on_train_epoch_start)
        model.add_callback("on_train_batch_end", on_train_batch_end)
        model.add_callback("on_train_epoch_end", on_train_epoch_end)
        model.add_callback("on_train_end", on_train_end)

        train_kwargs: dict[str, Any] = {
            "data": str(data_yaml_used),
            "epochs": epochs,
            "batch": batch_size,
            "imgsz": image_size,
            "patience": patience,
            "pretrained": pretrained,
            "project": str(project_arg),
            "name": run_name,
            "exist_ok": True,
            "workers": workers,
        }
        if device != "auto":
            train_kwargs["device"] = device
        if not augmentations:
            train_kwargs["augment"] = False
        if dry_run:
            train_kwargs["save"] = False
            train_kwargs["plots"] = False

        model.train(**train_kwargs)
    except TrainingCanceled:
        raise
    except Exception as exc:
        yolo_logger.exception("Training failed: %s", exc)
        raise
    finally:
        yolo_logger.removeHandler(log_handler)
        log_handler.close()

    if cleanup_tmp:
        cleanup_tmp.cleanup()
        log_store.pop(job.id, None)

    if job.status == status_canceled:
        return {"canceled": True}

    if dry_run:
        return {"dry_run": True}

    weights_dir = run_dir / "weights"
    result = {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "weights": {
            "best": str(weights_dir / "best.pt"),
            "last": str(weights_dir / "last.pt"),
        },
        "log": str(log_path) if log_path else None,
    }
    return result
