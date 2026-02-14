// src/hooks/useLibraryState.ts
import { useEffect, useMemo, useRef, useState } from "react";
import {
    fetchVolumes,
    fetchPages,
    absolutizeImageUrl,
    createVolume as createVolumeApi,
    uploadVolumePage,
    deleteVolumePage,
    importVolumes,
    detectMissingVolumes,
    pruneMissingVolumes,
    importPages,
    detectMissingPages,
    pruneMissingPages,
    fetchBoxDetectionProfiles,
    fetchOcrProviders,
    fetchTranslationProviders,
} from "../api";
import type {
    BoxDetectionProfile,
    Volume,
    PageInfo,
    OcrProvider,
    TranslationProvider,
} from "../types";

const LIBRARY_SELECTION_KEY = "mangayaku.translate.selection";

type LibrarySelection = {
    volumeId: string;
    pageIndex: number;
    filename: string;
};

let cachedSelection: LibrarySelection = {
    volumeId: "",
    pageIndex: 0,
    filename: "",
};

function readLibrarySelection(): LibrarySelection {
    if (typeof window === "undefined") {
        return cachedSelection;
    }
    try {
        const raw = window.sessionStorage.getItem(LIBRARY_SELECTION_KEY);
        if (!raw) {
            return cachedSelection;
        }
        const parsed = JSON.parse(raw) as Partial<LibrarySelection>;
        const volumeId =
            typeof parsed.volumeId === "string" ? parsed.volumeId : "";
        const pageIndex =
            typeof parsed.pageIndex === "number" && Number.isFinite(parsed.pageIndex)
                ? Math.max(0, Math.floor(parsed.pageIndex))
                : 0;
        const filename =
            typeof parsed.filename === "string" ? parsed.filename : "";
        const selection = { volumeId, pageIndex, filename };
        cachedSelection = selection;
        return selection;
    } catch {
        return cachedSelection;
    }
}

function writeLibrarySelection(selection: LibrarySelection) {
    cachedSelection = selection;
    if (typeof window === "undefined") {
        return;
    }
    try {
        window.sessionStorage.setItem(
            LIBRARY_SELECTION_KEY,
            JSON.stringify(selection),
        );
    } catch {
        // ignore storage failures
    }
}

export function useLibraryState() {
    const initialSelection = readLibrarySelection();
    const [volumes, setVolumes] = useState<Volume[]>([]);
    const [selectedVolumeId, setSelectedVolumeId] = useState<string>(
        initialSelection.volumeId,
    );
    const [pages, setPages] = useState<PageInfo[]>([]);
    const [pageIndex, setPageIndex] = useState(initialSelection.pageIndex);
    const prevVolumeIdRef = useRef<string | null>(null);
    const restoreSelectionRef = useRef({
        volumeId: initialSelection.volumeId,
        pageIndex: initialSelection.pageIndex,
        filename: initialSelection.filename,
        consumed: false,
    });

    const [error, setError] = useState<string | null>(null);
    const [loadingVolumes, setLoadingVolumes] = useState<boolean>(true);
    const [loadingPages, setLoadingPages] = useState<boolean>(false);

    // Box detection profiles + selection
    const [boxDetectionProfiles, setBoxDetectionProfiles] = useState<
        BoxDetectionProfile[]
    >([]);
    const [boxDetectionProfileId, setBoxDetectionProfileId] =
        useState<string>("");

    // OCR providers + selection
    const [ocrProviders, setOcrProviders] = useState<OcrProvider[]>([]);
    const [ocrEngineId, setOcrEngineId] = useState<string>("");

    // Translation providers + selection
    const [translationProviders, setTranslationProviders] = useState<
        TranslationProvider[]
    >([]);
    const [translationProfileId, setTranslationProfileId] =
        useState<string>("");

    // -----------------------------
    // Load OCR providers on mount
    // -----------------------------
    useEffect(() => {
        let cancelled = false;

        const loadOcrProviders = async () => {
            try {
                const providers = await fetchOcrProviders();
                if (cancelled) return;

                setOcrProviders(providers);

                if (!ocrEngineId) {
                    const firstEnabled = providers.find((p) => p.enabled);
                    if (firstEnabled) {
                        setOcrEngineId(firstEnabled.id);
                    }
                }
            } catch (err) {
                console.error("Failed to load OCR providers", err);
            }
        };

        void loadOcrProviders();

        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const applyBoxDetectionProfiles = (
        profiles: BoxDetectionProfile[],
        preserveSelection: boolean,
    ) => {
        setBoxDetectionProfiles(profiles);
        setBoxDetectionProfileId((prev) => {
            const hasPrev = prev
                ? profiles.some((p) => p.enabled && p.id === prev)
                : false;
            if (preserveSelection && hasPrev) {
                return prev;
            }
            const firstEnabled = profiles.find((p) => p.enabled);
            return firstEnabled ? firstEnabled.id : "";
        });
    };

    // -----------------------------
    // Load box detection profiles on mount
    // -----------------------------
    useEffect(() => {
        let cancelled = false;

        const loadBoxDetectionProfiles = async () => {
            try {
                const profiles = await fetchBoxDetectionProfiles();
                if (cancelled) return;
                applyBoxDetectionProfiles(profiles, true);
            } catch (err) {
                console.error("Failed to load box detection profiles", err);
            }
        };

        void loadBoxDetectionProfiles();

        return () => {
            cancelled = true;
        };
    }, []);

    // -----------------------------
    // Load translation providers on mount
    // -----------------------------
    useEffect(() => {
        let cancelled = false;

        const loadTranslationProviders = async () => {
            try {
                const providers = await fetchTranslationProviders();
                if (cancelled) return;

                setTranslationProviders(providers);

                if (!translationProfileId) {
                    const firstEnabled = providers.find((p) => p.enabled);
                    if (firstEnabled) {
                        setTranslationProfileId(firstEnabled.id);
                    }
                }
            } catch (err) {
                console.error("Failed to load translation providers", err);
            }
        };

        void loadTranslationProviders();

        return () => {
            cancelled = true;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // -----------------------------
    // Load volumes on mount
    // -----------------------------
    useEffect(() => {
        let cancelled = false;

        const loadVolumes = async () => {
            try {
                setError(null);
                const vs = await fetchVolumes();
                if (cancelled) return;

                setVolumes(vs);
                setSelectedVolumeId((prev) => {
                    if (prev && vs.some((v) => v.id === prev)) {
                        return prev;
                    }
                    return vs.length > 0 ? vs[0].id : "";
                });
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to load volumes", err);
                setError("Failed to load volumes. Check backend / CORS.");
            } finally {
                if (!cancelled) {
                    setLoadingVolumes(false);
                }
            }
        };

        void loadVolumes();

        return () => {
            cancelled = true;
        };
    }, []);

    // -----------------------------
    // Load pages when volume changes
    // -----------------------------
    useEffect(() => {
        if (!selectedVolumeId) {
            setPages([]);
            setPageIndex(0);
            setLoadingPages(false);
            return;
        }
        if (loadingVolumes && volumes.length === 0) {
            return;
        }
        if (volumes.length > 0 && !volumes.some((v) => v.id === selectedVolumeId)) {
            setSelectedVolumeId("");
            setPages([]);
            setPageIndex(0);
            return;
        }

        let cancelled = false;

        const volumeChanged = prevVolumeIdRef.current !== selectedVolumeId;
        prevVolumeIdRef.current = selectedVolumeId;

        const loadPages = async () => {
            try {
                setLoadingPages(true);
                setError(null);

                const ps = await fetchPages(selectedVolumeId);
                if (cancelled) return;

                setPages(ps);
                setPageIndex((prev) => {
                    if (ps.length === 0) {
                        return 0;
                    }
                    if (prev < 0) {
                        return 0;
                    }
                    const maxIndex = ps.length - 1;
                    if (volumeChanged) {
                        const restore = restoreSelectionRef.current;
                        if (
                            !restore.consumed &&
                            restore.volumeId &&
                            restore.volumeId === selectedVolumeId
                        ) {
                            restore.consumed = true;
                            if (restore.filename) {
                                const matchIndex = ps.findIndex(
                                    (p) => p.filename === restore.filename,
                                );
                                if (matchIndex >= 0) {
                                    return matchIndex;
                                }
                            }
                            if (restore.pageIndex > maxIndex) {
                                return maxIndex;
                            }
                            return Math.max(0, restore.pageIndex);
                        }
                        return 0;
                    }
                    return prev > maxIndex ? maxIndex : prev;
                });
            } catch (err) {
                if (cancelled) return;
                console.error("Failed to load pages", err);
                const message =
                    err instanceof Error ? err.message : "Failed to load pages.";
                if (
                    message.includes("HTTP 404") ||
                    message.includes("Volume not found")
                ) {
                    setSelectedVolumeId("");
                    setPages([]);
                    setPageIndex(0);
                    setError("Volume missing on disk. Sync or recreate.");
                    return;
                }
                setError("Failed to load pages. Check backend / CORS.");
            } finally {
                if (!cancelled) {
                    setLoadingPages(false);
                }
            }
        };

        void loadPages();

        return () => {
            cancelled = true;
        };
    }, [loadingVolumes, volumes, selectedVolumeId]);

    // -----------------------------
    // Manual refresh
    // -----------------------------
    const refreshLibrary = async () => {
        try {
            setError(null);
            setLoadingVolumes(true);

            const vs = await fetchVolumes();
            setVolumes(vs);

            setSelectedVolumeId((prev) => {
                if (!vs.length) return "";
                if (prev && vs.some((v) => v.id === prev)) {
                    return prev;
                }
                return vs[0].id;
            });
        } catch (err) {
            console.error("Failed to refresh volumes", err);
            setError("Failed to refresh volumes. Check backend / CORS.");
        } finally {
            setLoadingVolumes(false);
        }
    };

    const refreshBoxDetectionProfiles = async () => {
        try {
            const profiles = await fetchBoxDetectionProfiles();
            applyBoxDetectionProfiles(profiles, true);
        } catch (err) {
            console.error("Failed to refresh box detection profiles", err);
        }
    };

    const addPageFromClipboard = async (
        file: File,
        volumeIdOverride?: string,
        opts?: { insertBefore?: string; insertAfter?: string },
    ) => {
        const targetVolumeId = volumeIdOverride || selectedVolumeId;
        if (!targetVolumeId) {
            setError("Select or create a volume first.");
            return;
        }
        try {
            const page = await uploadVolumePage(targetVolumeId, file, opts);
            const updatedPages = await fetchPages(targetVolumeId);
            setPages(updatedPages);
            setSelectedVolumeId(targetVolumeId);
            const index = updatedPages.findIndex(
                (p) => p.filename === page.filename,
            );
            setPageIndex(
                index >= 0 ? index : Math.max(updatedPages.length - 1, 0),
            );
            setVolumes((prev) =>
                prev.map((volume) =>
                    volume.id === targetVolumeId
                        ? {
                              ...volume,
                              pageCount: Math.max(
                                  volume.pageCount,
                                  updatedPages.length,
                              ),
                          }
                        : volume,
                ),
            );
            setError(null);
        } catch (err) {
            console.error("Failed to upload page", err);
            if (err instanceof Error && err.message) {
                setError(err.message.replace("Failed to upload page: ", ""));
            } else {
                setError("Failed to upload page.");
            }
        }
    };

    const createVolume = async (name: string) => {
        try {
            const volume = await createVolumeApi(name);
            setVolumes((prev) => {
                const next = prev.filter((v) => v.id !== volume.id);
                return [volume, ...next];
            });
            setSelectedVolumeId(volume.id);
            setPageIndex(0);
            return volume;
        } catch (err) {
            console.error("Failed to create volume", err);
            throw err;
        }
    };

    const importVolumesFromDisk = async () => {
        const volumesResult = await importVolumes();
        const pagesResult = await importPages();
        if (volumesResult.imported > 0 || pagesResult.imported > 0) {
            await refreshLibrary();
        }
        return {
            volumesImported: volumesResult.imported,
            pagesImported: pagesResult.imported,
        };
    };

    const detectMissingVolumesInDb = async () => {
        const [volumes, pages] = await Promise.all([
            detectMissingVolumes(),
            detectMissingPages(),
        ]);
        return { volumes, pages };
    };

    const pruneMissingVolumesInDb = async (ids: string[], pages: { volumeId: string; filename: string }[]) => {
        const [volumesResult, pagesResult] = await Promise.all([
            pruneMissingVolumes(ids),
            pruneMissingPages(pages),
        ]);
        if (volumesResult.deleted > 0 || pagesResult.deleted > 0) {
            await refreshLibrary();
        }
        return {
            volumesDeleted: volumesResult.deleted,
            pagesDeleted: pagesResult.deleted,
        };
    };

    const deletePageFromVolume = async (
        volumeId: string,
        filename: string,
    ) => {
        if (!volumeId || !filename) {
            return;
        }
        try {
            await deleteVolumePage(volumeId, filename);
            const updatedPages = await fetchPages(volumeId);
            setPages(updatedPages);
            setPageIndex((prev) => {
                if (updatedPages.length === 0) {
                    return 0;
                }
                if (prev >= updatedPages.length) {
                    return updatedPages.length - 1;
                }
                return prev;
            });
            setVolumes((prev) =>
                prev.map((volume) =>
                    volume.id === volumeId
                        ? { ...volume, pageCount: updatedPages.length }
                        : volume,
                ),
            );
            setError(null);
        } catch (err) {
            console.error("Failed to delete page", err);
            if (err instanceof Error && err.message) {
                setError(err.message.replace("Failed to delete page: ", ""));
            } else {
                setError("Failed to delete page.");
            }
        }
    };

    // -----------------------------
    // Derived values
    // -----------------------------
    const hasPrev = pageIndex > 0;
    const hasNext = pageIndex < pages.length - 1;

    const currentPage = useMemo(
        () =>
            pageIndex >= 0 && pageIndex < pages.length
                ? pages[pageIndex]
                : undefined,
        [pages, pageIndex],
    );

    const currentPageImageUrl = useMemo(
        () => (currentPage ? absolutizeImageUrl(currentPage) : null),
        [currentPage],
    );

    useEffect(() => {
        if (!selectedVolumeId) {
            return;
        }
        const filename = currentPage?.filename ?? "";
        writeLibrarySelection({ volumeId: selectedVolumeId, pageIndex, filename });
    }, [selectedVolumeId, pageIndex, currentPage]);

    const handlePrev = () => {
        if (hasPrev) setPageIndex((i) => i - 1);
    };

    const handleNext = () => {
        if (hasNext) {
            setPageIndex((i) => i + 1);
        }
    };

    return {
        // data
        volumes,
        selectedVolumeId,
        pages,
        pageIndex,
        currentPage,
        currentPageImageUrl,
        boxDetectionProfiles,
        boxDetectionProfileId,
        ocrProviders,
        ocrEngineId,
        translationProviders,
        translationProfileId,

        // status
        error,
        loadingVolumes,
        loadingPages,

        // setters / actions
        setSelectedVolumeId,
        setPageIndex,
        setBoxDetectionProfileId,
        setOcrEngineId,
        setTranslationProfileId,
        handlePrev,
        handleNext,
        refreshLibrary,
        createVolume,
        addPageFromClipboard,
        deletePageFromVolume,
        importVolumesFromDisk,
        detectMissingVolumesInDb,
        pruneMissingVolumesInDb,
        refreshBoxDetectionProfiles,
    };
}

