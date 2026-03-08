# backend-python/tests/api/test_utility_job_routes.py
"""Route tests for persisted utility workflow creation endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from api.routers.jobs import routes as jobs_routes
from api.schemas.jobs import (
    CreateBoxDetectionJobRequest,
    CreatePrepareDatasetJobRequest,
    CreateTrainModelJobRequest,
)


@pytest.mark.asyncio
async def test_box_detection_route_creates_persisted_workflow() -> None:
    req = CreateBoxDetectionJobRequest(volumeId="vol-a", filename="001.jpg")

    with patch(
        "api.routers.jobs.routes.create_box_detection_workflow",
        return_value="wf-box-1",
    ) as create_mock:
        response = await jobs_routes.create_box_detection_job(req)

    assert response.jobId == "wf-box-1"
    create_mock.assert_called_once_with(req)


def test_box_detection_request_defaults_to_preserve_existing_boxes() -> None:
    req = CreateBoxDetectionJobRequest(volumeId="vol-a", filename="001.jpg")
    assert req.replaceExisting is False


@pytest.mark.asyncio
async def test_prepare_dataset_route_creates_persisted_workflow() -> None:
    req = CreatePrepareDatasetJobRequest(sources=["manga109s:demo"])

    with (
        patch("api.routers.jobs.routes.resolve_training_sources") as resolve_mock,
        patch(
            "api.routers.jobs.routes.create_prepare_dataset_workflow",
            return_value="wf-dataset-1",
        ) as create_mock,
    ):
        response = await jobs_routes.create_prepare_dataset_job(req)

    assert response.jobId == "wf-dataset-1"
    resolve_mock.assert_called_once()
    create_mock.assert_called_once_with(req)


@pytest.mark.asyncio
async def test_train_model_route_creates_persisted_workflow() -> None:
    req = CreateTrainModelJobRequest(dataset_id="dataset-1")

    with (
        patch("api.routers.jobs.routes.resolve_prepared_dataset") as resolve_mock,
        patch(
            "api.routers.jobs.routes.create_train_model_workflow",
            return_value="wf-train-1",
        ) as create_mock,
    ):
        response = await jobs_routes.create_train_model_job(req)

    assert response.jobId == "wf-train-1"
    resolve_mock.assert_called_once_with("dataset-1")
    create_mock.assert_called_once_with(req)
