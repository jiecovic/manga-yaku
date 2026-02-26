// src/hooks/usePageJobActions.ts
import type {Box} from "../types";
import {
    createAgentTranslatePageJob,
    createOcrBoxJob,
    createOcrPageJob,
    createTranslateBoxJob,
    createTranslatePageJob,
} from "../api";
import {usePage} from "../context/usePage";
import { useAgentSettings } from "../context/AgentSettingsContext";
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
    handleTranslatePage: () => Promise<void>;
    handleAgentTranslatePage: () => Promise<void>;
}

export function usePageJobActions({
    boxes,
    ocrProfileId,
    translationProfileId,
    boxDetectionProfileId,
}: UsePageJobActionsArgs): UsePageJobActionsResult {
    const {volumeId, filename} = usePage();
    const { ocrProfiles } = useAgentSettings();
    const { settings } = useSettings();
    const agentDetectionProfileId =
        typeof settings?.values?.["agent.translate.detection_profile_id"] === "string"
            ? settings.values["agent.translate.detection_profile_id"].trim()
            : "";
    const translateBoxUseContext =
        typeof settings?.values?.["translation.single_box.use_context"] === "boolean"
            ? settings.values["translation.single_box.use_context"]
            : true;
    const standaloneOcrJobsDetached = false;
    const standaloneTranslationPageJobsDetached = true;
    const standaloneTranslationBoxJobsDetached = false;

    // =========================================
    // TRANSLATE PAGE (classic)
    // =========================================
    const handleTranslatePage = async () => {
        if (standaloneTranslationPageJobsDetached) return;
        if (!volumeId || !filename) return;
        if (!boxes || boxes.length === 0) return;

        const profileId = translationProfileId || "openai_fast_translate";
        try {
            console.log(
                `Queuing TRANSLATE page job for ${volumeId}/${filename}`,
            );

            await createTranslatePageJob({
                profileId,
                volumeId,
                filename,
                usePageContext: false,
                skipExisting: true,
            });
        } catch (err) {
            console.error("Failed to queue translate page job", err);
        }
    };

    // =========================================
    // AGENT TRANSLATE PAGE (detect + multi-OCR + translate)
    // =========================================
    const handleAgentTranslatePage = async () => {
        if (!volumeId || !filename) return;

        try {
            console.log(
                `Queuing AGENT translate page job for ${volumeId}/${filename}`,
            );

            const configuredProfiles = ocrProfiles?.profiles ?? [];
            const ocrProfilesForAgent = configuredProfiles
                .filter((profile) => profile.enabled && profile.agent_enabled)
                .map((profile) => profile.id);
            if (!ocrProfilesForAgent.length) {
                const primaryOcr = ocrProfileId || "manga_ocr_default";
                ocrProfilesForAgent.push(primaryOcr);
            }

            await createAgentTranslatePageJob({
                volumeId,
                filename,
                detectionProfileId:
                    agentDetectionProfileId ||
                    boxDetectionProfileId ||
                    undefined,
                ocrProfiles: ocrProfilesForAgent,
            });
        } catch (err) {
            console.error("Failed to queue agent translate job for page", err);
        }
    };

    // =========================================
    // OCR PAGE
    // (only boxes without OCR text)
    // =========================================
    const handleOcrPage = async () => {
        if (standaloneOcrJobsDetached) return;
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
        if (standaloneOcrJobsDetached) return;
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
        if (standaloneTranslationBoxJobsDetached) return;
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
        handleTranslatePage,
        handleAgentTranslatePage,
    };
}
