// src/types.ts

export interface Volume {
    id: string;
    name: string;
    pageCount: number;
    coverImageUrl?: string | null;
}

export interface MissingVolume {
    id: string;
    name: string;
}

export interface MissingPage {
    volumeId: string;
    filename: string;
}

export interface PageInfo {
    id: string;
    volumeId: string;
    filename: string;
    relPath: string;
    imageUrl?: string | null;
    missing?: boolean;
}

export type BoxType = "text" | "panel" | "face" | "body";
export type BoxSource = "manual" | "detect";

export interface Box {
    id: number;
    orderIndex?: number;
    x: number;
    y: number;
    width: number;
    height: number;
    type: BoxType;
    source?: BoxSource;
    runId?: string | null;
    modelId?: string | null;
    modelLabel?: string | null;
    modelVersion?: string | null;
    modelPath?: string | null;
    modelHash?: string | null;
    modelTask?: string | null;

    // Editable optional fields
    text?: string;         // OCR result (text boxes only)
    translation?: string;  // Translation (text boxes only)
    note?: string;         // Agent/editor note (text boxes only)
}

export interface BoxDetectionProfile {
    id: string;
    label: string;
    description?: string | null;
    provider?: string | null;
    enabled: boolean;
    classes?: string[];
    tasks?: string[];
}


export interface OcrProvider {
    id: string;                  // "manga_ocr"
    label: string;               // "manga-ocr (local)"
    description?: string | null;
    kind: string;                // "local" | "remote" | ...
    enabled: boolean;
}

export interface TranslationProvider {
    id: string;                  // "openai_fast_translate"
    label: string;               // "OpenAI (fast, JA->EN)"
    description?: string | null;
    kind: string;                // "remote" | "local" | ...
    enabled: boolean;
}

export interface AgentSession {
    id: string;
    volumeId: string;
    title: string;
    modelId?: string | null;
    createdAt: string;
    updatedAt: string;
}

export interface AgentMessage {
    id: number;
    sessionId: string;
    role: string;
    content: string;
    createdAt: string;
    meta?: Record<string, unknown> | null;
}

export interface AgentModel {
    id: string;
    label: string;
}
export type TrainingSourceType = "manga109s" | "yolo" | "custom-db" | "unknown";

export interface TrainingSource {
    id: string;
    label: string;
    type: TrainingSourceType;
    path?: string | null;
    available: boolean;
    description?: string | null;
    stats?: {
        volumes?: number | null;
        images?: number | null;
        annotations?: string[];
    };
}

export interface TrainingDataset {
    id: string;
    path: string;
    created_at?: string | null;
    targets?: string[];
    val_split?: number | null;
    test_split?: number | null;
    image_mode?: string | null;
    seed?: number | null;
    stats?: {
        train_images?: number | null;
        val_images?: number | null;
        test_images?: number | null;
        train_labels?: number | null;
        val_labels?: number | null;
        test_labels?: number | null;
    };
}
