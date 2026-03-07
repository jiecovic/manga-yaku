# backend-python/tests/infra/training/test_dataset_builder.py
"""Tests for dataset builder cancelation behavior."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from infra.jobs.exceptions import JobCanceled
from infra.training.dataset_builder import prepare_dataset


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
                prepare_dataset(
                    dataset_id="dataset-a",
                    source_dirs=[Path("/tmp/source")],
                    is_canceled=cancel_cb,
                ),
            assert not out_dir.exists()

    assert seen_cancel_cb is cancel_cb
