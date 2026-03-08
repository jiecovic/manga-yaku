# backend-python/tests/infra/training/test_dataset_builder.py
"""Tests for dataset builder cancelation behavior."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from infra.jobs.exceptions import JobCanceled
from infra.training.dataset_builder import (
    BuildStats,
    _canonical_source_annotation_tag,
    prepare_dataset,
)


def test_prepare_dataset_cleans_partial_output_on_cancel() -> None:
    seen_cancel_cb = None

    def cancel_cb() -> bool:
        return False

    def _prepare_manga109s(**kwargs):
        nonlocal seen_cancel_cb
        seen_cancel_cb = kwargs.get("is_canceled")
        raise JobCanceled("Canceled")

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        out_dir = root / "dataset-a"
        with (
            patch("infra.training.dataset_builder.TRAINING_PREPARED_ROOT", root),
            patch(
                "infra.training.dataset_builder._count_manga109s_volumes",
                return_value=1,
            ),
            patch(
                "infra.training.dataset_builder._prepare_manga109s",
                side_effect=_prepare_manga109s,
            ),
        ):
            with pytest.raises(JobCanceled):
                (
                    prepare_dataset(
                        dataset_id="dataset-a",
                        source_dirs=[Path("/tmp/source")],
                        is_canceled=cancel_cb,
                    ),
                )
            assert not out_dir.exists()

    assert seen_cancel_cb is cancel_cb


def test_prepare_dataset_keeps_panel_as_canonical_target() -> None:
    seen_targets = None

    def fake_prepare_manga109s(**kwargs):
        nonlocal seen_targets
        seen_targets = list(kwargs.get("targets") or [])
        return BuildStats()

    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        with (
            patch("infra.training.dataset_builder.TRAINING_PREPARED_ROOT", root),
            patch(
                "infra.training.dataset_builder._count_manga109s_volumes",
                return_value=1,
            ),
            patch(
                "infra.training.dataset_builder._prepare_manga109s",
                side_effect=fake_prepare_manga109s,
            ),
        ):
            dataset_id, out_dir, _stats = prepare_dataset(
                dataset_id="dataset-a",
                source_dirs=[Path("/tmp/source")],
                targets=["text", "panel", "panel"],
            )

            assert out_dir.is_dir()

    assert dataset_id == "dataset-a"
    assert seen_targets == ["text", "panel"]


def test_canonical_source_annotation_tag_maps_frame_to_panel() -> None:
    assert _canonical_source_annotation_tag("frame") == "panel"
    assert _canonical_source_annotation_tag("panel") == "panel"
    assert _canonical_source_annotation_tag("text") == "text"
