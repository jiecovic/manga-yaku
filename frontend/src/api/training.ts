// src/api/training.ts
import type { TrainingDataset, TrainingSource } from "../types";
import type { CreateJobResponse } from "./jobs";
import { API_BASE, apiFetch, getJson } from "./client";

export interface CreatePrepareDatasetJobRequest {
    dataset_id?: string;
    sources: string[];
    targets?: string[];
    val_split?: number;
    test_split?: number;
    link_mode?: string;
    seed?: number;
    overwrite?: boolean;
}

export interface CreateTrainModelJobRequest {
    dataset_id: string;
    model_family: string;
    model_size: string;
    pretrained: boolean;
    epochs: number;
    batch_size: number;
    workers: number;
    image_size: number;
    device: string;
    patience: number;
    augmentations: boolean;
    dry_run: boolean;
}

export interface TrainingModelsResponse {
    ultralytics_version: string;
    families: string[];
}

export function fetchTrainingSources(): Promise<TrainingSource[]> {
    return getJson<TrainingSource[]>(`${API_BASE}/api/training/sources`);
}

export function fetchTrainingDatasets(): Promise<TrainingDataset[]> {
    return getJson<TrainingDataset[]>(`${API_BASE}/api/training/datasets`);
}

export function fetchTrainingModels(): Promise<TrainingModelsResponse> {
    return getJson<TrainingModelsResponse>(`${API_BASE}/api/training/models`);
}

export async function createPrepareDatasetJob(
    payload: CreatePrepareDatasetJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/prepare_dataset`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}

export async function createTrainModelJob(
    payload: CreateTrainModelJobRequest,
): Promise<CreateJobResponse> {
    const res = await apiFetch(`${API_BASE}/api/jobs/train_model`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
        },
        body: JSON.stringify(payload),
    });

    return res.json() as Promise<CreateJobResponse>;
}
