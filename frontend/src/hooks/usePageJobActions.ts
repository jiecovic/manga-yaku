// src/hooks/usePageJobActions.ts
import { useRef } from "react";
import type {Box} from "../types";
import {
    createPageTranslationJob,
    createOcrBoxJob,
    createOcrPageJob,
    createTranslateBoxJob,
} from "../api";
import {usePage} from "../context/usePage";
import { useJobs } from "../context/useJobs";
import { useWorkflowSettings } from "../context/WorkflowSettingsContext";
import { useSettings } from "../context/SettingsContext";
import { normalizeBoxType } from "../utils/boxes";

interface UsePageJobActionsArgs {
    boxes: Box[];
    ocrProfileId: string;
    translationProfileId: string;
    boxDetectionProfileId: string;
}

interface UsePageJobActionsResult {
    handleOcrPage: () => Promise<void>;
    handleOcrBox: (id: number) => Promise<void>;
    handleTranslateBox: (id: number) => Promise<void>;
    handlePageTranslationWorkflow: () => Promise<void>;
}

export function usePageJobActions({
    boxes,
    ocrProfileId,
    translationProfileId,
    boxDetectionProfileId,
}: UsePageJobActionsArgs): UsePageJobActionsResult {
    const {volumeId, filename} = usePage();
    const { jobCapabilities, jobs } = useJobs();
    const { ocrProfiles } = useWorkflowSettings();
    const { settings } = useSettings();
    const pageTranslationDetectionProfileId =
        typeof settings?.values?.["page_translation.detection_profile_id"] === "string"
            ? settings.values["page_translation.detection_profile_id"].trim()
            : "";
    const translateBoxUseContext =
        typeof settings?.values?.["translation.single_box.use_context"] === "boolean"
            ? settings.values["translation.single_box.use_context"]
            : true;
    const inFlightAgentRequestKeyRef = useRef<string | null>(null);

    const createIdempotencyKey = () => {
        // Reuse browser UUID when available; fallback keeps dev/tests working.
        if (typeof globalThis.crypto?.randomUUID === "function") {
            return globalThis.crypto.randomUUID();
        }
        return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    };

    // =========================================
    // PAGE TRANSLATION WORKFLOW (detect + multi-OCR + translate)
    // =========================================
    const handlePageTranslationWorkflow = async () => {
        if (!volumeId || !filename) return;

        const activeJob = jobs.find((job) => {
            if (job.type !== "page_translation") {
                return false;
            }
            if (job.status !== "queued" && job.status !== "running") {
                return false;
            }
            const jobVolumeId = String(job.payload?.volumeId ?? "").trim();
            const jobFilename = String(job.payload?.filename ?? "").trim();
            return jobVolumeId === volumeId && jobFilename === filename;
        });
        if (activeJob) {
            window.alert(
                "Page translation is already queued or running for this page. Please wait until it finishes.",
            );
            return;
        }

        const inFlightKey = inFlightAgentRequestKeyRef.current;
        if (inFlightKey) {
            window.alert(
                "Page translation request is already being submitted for this page. Please wait.",
            );
            return;
        }
        const idempotencyKey = inFlightKey || createIdempotencyKey();
        if (!inFlightKey) {
            inFlightAgentRequestKeyRef.current = idempotencyKey;
        }

        try {
            console.log(
                `Queuing PAGE TRANSLATION workflow for ${volumeId}/${filename}`,
            );

            const configuredProfiles = ocrProfiles?.profiles ?? [];
            const ocrProfilesForAgent = configuredProfiles
                .filter((profile) => profile.enabled && profile.page_translation_enabled)
                .map((profile) => profile.id);
            if (!ocrProfilesForAgent.length) {
                const primaryOcr = ocrProfileId || "manga_ocr_default";
                ocrProfilesForAgent.push(primaryOcr);
            }

            await createPageTranslationJob({
                volumeId,
                filename,
                detectionProfileId:
                    pageTranslationDetectionProfileId ||
                    boxDetectionProfileId ||
                    undefined,
                ocrProfiles: ocrProfilesForAgent,
            }, {
                idempotencyKey,
            });
        } catch (err) {
            console.error(
                "Failed to queue page translation workflow for page",
                err,
            );
        } finally {
            if (inFlightAgentRequestKeyRef.current === idempotencyKey) {
                inFlightAgentRequestKeyRef.current = null;
            }
        }
    };

    // =========================================
    // OCR PAGE
    // (only boxes without OCR text)
    // =========================================
    const handleOcrPage = async () => {
        if (!jobCapabilities.ocr_page.enabled) return;
        if (!volumeId || !filename) return;
        if (!boxes || boxes.length === 0) return;

        const profileId = ocrProfileId || "manga_ocr_default";
        const profileIds = [profileId];

        try {
            console.log(
                `Queuing OCR page job for ${volumeId}/${filename} with profiles ${profileIds.join(",")}`,
            );

            await createOcrPageJob({
                profileId,
                profileIds,
                volumeId,
                filename,
                skipExisting: true,
            });
        } catch (err) {
            console.error("Failed to queue OCR job for page", err);
        }
    };

    // =========================================
    // OCR SINGLE BOX
    // =========================================
    const handleOcrBox = async (id: number) => {
        if (!jobCapabilities.ocr_box.enabled) return;
        if (!volumeId || !filename) return;

        const box = boxes.find(
            (b) => b.id === id && normalizeBoxType(b.type) === "text",
        );
        if (!box) return;

        const profileId = ocrProfileId || "manga_ocr_default";

        try {
            console.log(
                `Queuing OCR job for box ${id} on ${volumeId}/${filename} with profile ${profileId}`,
            );

            const res = await createOcrBoxJob({
                profileId,
                volumeId,
                filename,
                x: box.x,
                y: box.y,
                width: box.width,
                height: box.height,
                boxId: box.id,
                boxOrder:
                    box.orderIndex && box.orderIndex > 0
                        ? box.orderIndex
                        : undefined,
            });

            console.log("Queued OCR job", res.jobId, "for box", box.id);
        } catch (err) {
            console.error("Failed to queue OCR job for box", id, err);
        }
    };

    // =========================================
    // TRANSLATE SINGLE BOX
    // (re-run allowed, still requires OCR text)
    // =========================================
    const handleTranslateBox = async (id: number) => {
        if (!jobCapabilities.translate_box.enabled) return;
        if (!volumeId || !filename) return;

        const box = boxes.find(
            (b) => b.id === id && normalizeBoxType(b.type) === "text",
        );
        if (!box) return;

        const profileId = translationProfileId || "openai_fast_translate";
        const sourceText = box.text?.trim();
        if (!sourceText) {
            console.log("No OCR text to translate for box", id);
            return;
        }

        try {
            console.log(
                `Queuing TRANSLATE job for box ${id} on ${volumeId}/${filename} with profile ${profileId}`,
            );

            const res = await createTranslateBoxJob({
                profileId,
                volumeId,
                filename,
                boxId: id,
                usePageContext: translateBoxUseContext,
                boxOrder:
                    box.orderIndex && box.orderIndex > 0
                        ? box.orderIndex
                        : undefined,
            });

            console.log("Queued TRANSLATE job", res.jobId, "for box", box.id);
        } catch (err) {
            console.error("Failed to queue translation job for box", id, err);
        }
    };

    return {
        handleOcrPage,
        handleOcrBox,
        handleTranslateBox,
        handlePageTranslationWorkflow,
    };
}
