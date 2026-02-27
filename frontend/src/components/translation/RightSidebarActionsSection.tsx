// src/components/translation/RightSidebarActionsSection.tsx
import { useEffect, useState } from "react";
import { CollapsibleSection } from "./CollapsibleSection";
import type { BoxDetectionProfile } from "../../types";
import { ui } from "../../ui/tokens";
import { Button, Field, Select } from "../../ui/primitives";
import { normalizeBoxType } from "../../utils/boxes";
import { useJobs } from "../../context/useJobs";

interface ActionsSectionProps {
    boxDetectionProfiles: BoxDetectionProfile[];
    boxDetectionProfileId: string;
    onChangeBoxDetectionProfile: (id: string) => void;
    boxDetectionTask: string;
    onChangeBoxDetectionTask: (task: string) => void;
    onRefreshBoxDetectionProfiles: () => Promise<void>;
    onOcrPage: () => void;
    onTranslatePage: () => void;
    onAgentTranslatePage: () => void;
    onClearBoxes: () => void;
    onClearOcrText: () => void;
    onClearTranslationText: () => void;

    // NEW
    onAutoDetectBoxes: () => void;
    onRefreshPageState: () => void;
    onOpenMemory: () => void;
    canOpenMemory: boolean;
}

export function RightSidebarActionsSection({
    boxDetectionProfiles,
    boxDetectionProfileId,
    onChangeBoxDetectionProfile,
    boxDetectionTask,
    onChangeBoxDetectionTask,
    onRefreshBoxDetectionProfiles,
    onOcrPage,
    onTranslatePage,
    onAgentTranslatePage,
    onClearBoxes,
    onClearOcrText,
    onClearTranslationText,
    onAutoDetectBoxes,
    onRefreshPageState,
    onOpenMemory,
    canOpenMemory,
}: ActionsSectionProps) {
    const { jobCapabilities } = useJobs();
    const [refreshingModels, setRefreshingModels] = useState(false);
    const loadingBoxDetectionProfiles = boxDetectionProfiles.length === 0;
    const enabledBoxDetectionProfiles = boxDetectionProfiles.filter(
        (profile) => profile.enabled,
    );
    const normalizedTask = normalizeBoxType(boxDetectionTask);
    const availableBoxDetectionProfiles = enabledBoxDetectionProfiles.filter(
        (profile) => {
            const tasks = profile.tasks ?? [];
            if (tasks.length > 0) {
                return tasks.some(
                    (task) => normalizeBoxType(task) === normalizedTask,
                );
            }
            const classes = profile.classes ?? [];
            if (classes.length === 0) {
                return true;
            }
            return classes.some(
                (name) => normalizeBoxType(name) === normalizedTask,
            );
        },
    );
    const selectedProfileId = availableBoxDetectionProfiles.some(
        (profile) => profile.id === boxDetectionProfileId,
    )
        ? boxDetectionProfileId
        : availableBoxDetectionProfiles[0]?.id ?? "";
    const hasAvailableBoxDetection = availableBoxDetectionProfiles.length > 0;
    const autoDetectDisabled =
        loadingBoxDetectionProfiles || !hasAvailableBoxDetection;
    const autoDetectReason = loadingBoxDetectionProfiles
        ? "Loading box detection models..."
        : !hasAvailableBoxDetection
        ? "No box detection models available for this task. Train a model to enable detection."
        : "";
    const translatePageDisabled = !jobCapabilities.translate_page.enabled;
    const translatePageDisabledReason = jobCapabilities.translate_page.reason ?? "";

    useEffect(() => {
        if (
            selectedProfileId &&
            selectedProfileId !== boxDetectionProfileId
        ) {
            onChangeBoxDetectionProfile(selectedProfileId);
        }
    }, [
        selectedProfileId,
        boxDetectionProfileId,
        onChangeBoxDetectionProfile,
    ]);

    const handleRefreshModels = async () => {
        if (refreshingModels) {
            return;
        }
        setRefreshingModels(true);
        try {
            await onRefreshBoxDetectionProfiles();
        } finally {
            setRefreshingModels(false);
        }
    };

    return (
        <CollapsibleSection title="Page Actions" defaultOpen>
            <div className="space-y-2">
                <Field label="Task" layout="row" labelClassName={ui.label}>
                    <Select
                        value={boxDetectionTask}
                        onChange={(e) =>
                            onChangeBoxDetectionTask(e.target.value)
                        }
                    >
                        <option value="text">Text boxes</option>
                        <option value="panel">Panels</option>
                        <option value="face">Faces</option>
                        <option value="body">Bodies</option>
                    </Select>
                </Field>

                <Field
                    label="Detection"
                    layout="row"
                    labelClassName={ui.label}
                    className="min-w-0"
                >
                    {loadingBoxDetectionProfiles && (
                        <div className={ui.mutedTextXs}>Loading...</div>
                    )}

                    {!loadingBoxDetectionProfiles &&
                        availableBoxDetectionProfiles.length === 0 && (
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                                <div className="flex flex-col">
                                    <div className={ui.mutedTextXs}>
                                        No models available for this task.
                                    </div>
                                    <div className={ui.mutedTextXs}>
                                        Train a model to enable detection.
                                    </div>
                                </div>
                                <Button
                                    type="button"
                                    variant="ghostSmall"
                                    onClick={handleRefreshModels}
                                    disabled={refreshingModels}
                                >
                                    Refresh
                                </Button>
                            </div>
                        )}

                    {!loadingBoxDetectionProfiles &&
                        availableBoxDetectionProfiles.length > 0 && (
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                                <Select
                                    value={selectedProfileId}
                                    onChange={(e) =>
                                        onChangeBoxDetectionProfile(
                                            e.target.value,
                                        )
                                    }
                                    className="flex-1 min-w-0"
                                >
                                    {availableBoxDetectionProfiles.map(
                                        (profile) => (
                                            <option
                                                key={profile.id}
                                                value={profile.id}
                                            >
                                                {profile.label}
                                            </option>
                                        ),
                                    )}
                                </Select>
                                <Button
                                    type="button"
                                    variant="ghostSmall"
                                    onClick={handleRefreshModels}
                                    disabled={refreshingModels}
                                >
                                    {refreshingModels ? "Refreshing..." : "Refresh"}
                                </Button>
                            </div>
                        )}
                </Field>

                {/* Row 1: Detection + OCR + Translate */}
                <div className="flex gap-2">
                    <Button
                        type="button"
                        variant="actionIndigo"
                        onClick={onAutoDetectBoxes}
                        disabled={autoDetectDisabled}
                        title={autoDetectDisabled ? autoDetectReason : undefined}
                    >
                        {normalizedTask === "panel"
                            ? "Auto detect panels"
                            : normalizedTask === "face"
                            ? "Auto detect faces"
                            : normalizedTask === "body"
                            ? "Auto detect bodies"
                            : "Auto detect text"}
                    </Button>

                    <Button
                        type="button"
                        variant="actionAmber"
                        onClick={onOcrPage}
                    >
                        OCR (all boxes)
                    </Button>

                    <Button
                        type="button"
                        variant="actionEmerald"
                        onClick={onTranslatePage}
                        disabled={translatePageDisabled}
                        title={
                            translatePageDisabled
                                ? translatePageDisabledReason || undefined
                                : undefined
                        }
                    >
                        Translate
                    </Button>
                </div>

                <div className="flex gap-2">
                    <Button
                        type="button"
                        variant="actionEmerald"
                        onClick={onAgentTranslatePage}
                    >
                        Agent translate
                    </Button>
                </div>

                {/* Row 2: Refresh + Clear Boxes */}
                <div className="flex gap-2">
                    <Button
                        type="button"
                        variant="actionSlate"
                        onClick={onRefreshPageState}
                    >
                        Refresh page
                    </Button>

                    <Button
                        type="button"
                        variant="actionRed"
                        onClick={onClearBoxes}
                    >
                        {normalizedTask === "panel"
                            ? "Clear panels"
                            : normalizedTask === "face"
                            ? "Clear faces"
                            : normalizedTask === "body"
                            ? "Clear bodies"
                            : "Clear text boxes"}
                    </Button>
                </div>

                {/* Row 3: Memory */}
                <div className="flex gap-2">
                    <Button
                        type="button"
                        variant="actionSlate"
                        onClick={onOpenMemory}
                        disabled={!canOpenMemory}
                    >
                        Memory
                    </Button>
                </div>

                {/* Row 3: Clear text */}
                <div className="flex gap-2">
                    <Button
                        type="button"
                        variant="actionSlateSmall"
                        onClick={onClearOcrText}
                    >
                        Clear OCR text
                    </Button>

                    <Button
                        type="button"
                        variant="actionSlateSmall"
                        onClick={onClearTranslationText}
                    >
                        Clear translations
                    </Button>
                </div>
            </div>
        </CollapsibleSection>
    );
}
