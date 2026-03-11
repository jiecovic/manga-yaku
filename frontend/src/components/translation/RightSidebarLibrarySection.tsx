// src/components/translation/RightSidebarLibrarySection.tsx
import { useState } from 'react';
import type { MissingPage, MissingVolume, Volume } from '../../types';
import { Button, Field, Select } from '../../ui/primitives';
import { ui } from '../../ui/tokens';
import { CollapsibleSection } from './CollapsibleSection';

interface LibrarySectionProps {
  volumes: Volume[];
  selectedVolumeId: string;
  loadingVolumes: boolean;
  loadingPages: boolean;
  onChangeVolume: (id: string) => void;
  onRefreshPages: () => void;
  onCreateVolume: (name: string) => Promise<Volume>;
  onImportVolumes: () => Promise<{
    volumesImported: number;
    pagesImported: number;
  }>;
  onDetectMissingVolumes: () => Promise<{
    volumes: MissingVolume[];
    pages: MissingPage[];
  }>;
  onPruneMissingVolumes: (
    ids: string[],
    pages: MissingPage[],
  ) => Promise<{ volumesDeleted: number; pagesDeleted: number }>;
}

export function RightSidebarLibrarySection({
  volumes,
  selectedVolumeId,
  loadingVolumes,
  loadingPages,
  onChangeVolume,
  onRefreshPages,
  onCreateVolume,
  onImportVolumes,
  onDetectMissingVolumes,
  onPruneMissingVolumes,
}: LibrarySectionProps) {
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [missingVolumes, setMissingVolumes] = useState<MissingVolume[]>([]);
  const [missingPages, setMissingPages] = useState<MissingPage[]>([]);
  const [showMissing, setShowMissing] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const openCreate = () => {
    setCreateName('');
    setCreateError(null);
    setShowCreate(true);
  };

  const closeCreate = () => {
    if (creating) {
      return;
    }
    setShowCreate(false);
  };

  const handleCreate = async () => {
    const trimmed = createName.trim();
    if (!trimmed) {
      setCreateError('Enter a volume name.');
      return;
    }

    setCreating(true);
    setCreateError(null);
    try {
      await onCreateVolume(trimmed);
      setShowCreate(false);
    } catch (err) {
      if (err instanceof Error && err.message) {
        setCreateError(err.message.replace('Failed to create volume: ', ''));
      } else {
        setCreateError('Failed to create volume.');
      }
    } finally {
      setCreating(false);
    }
  };

  const handleImport = async () => {
    setSyncError(null);
    setSyncing(true);
    try {
      const result = await onImportVolumes();
      if (result.volumesImported === 0 && result.pagesImported === 0) {
        setSyncError('No new folders found.');
      } else {
        setSyncError(`Imported ${result.volumesImported} volumes, ${result.pagesImported} pages.`);
      }
    } catch (err) {
      if (err instanceof Error && err.message) {
        setSyncError(err.message);
      } else {
        setSyncError('Failed to import volumes.');
      }
    } finally {
      setSyncing(false);
    }
  };

  const handleDetectMissing = async () => {
    setSyncError(null);
    setSyncing(true);
    try {
      const missing = await onDetectMissingVolumes();
      if (missing.volumes.length === 0 && missing.pages.length === 0) {
        setSyncError('No missing items detected.');
        return;
      }
      setMissingVolumes(missing.volumes);
      setMissingPages(missing.pages);
      setShowMissing(true);
    } catch (err) {
      if (err instanceof Error && err.message) {
        setSyncError(err.message);
      } else {
        setSyncError('Failed to detect missing volumes.');
      }
    } finally {
      setSyncing(false);
    }
  };

  const handlePruneMissing = async () => {
    setSyncError(null);
    setSyncing(true);
    try {
      const ids = missingVolumes.map((volume) => volume.id);
      if (ids.length === 0 && missingPages.length === 0) {
        setShowMissing(false);
        return;
      }
      await onPruneMissingVolumes(ids, missingPages);
      setShowMissing(false);
      setMissingVolumes([]);
      setMissingPages([]);
    } catch (err) {
      if (err instanceof Error && err.message) {
        setSyncError(err.message);
      } else {
        setSyncError('Failed to remove missing volumes.');
      }
    } finally {
      setSyncing(false);
    }
  };

  return (
    <CollapsibleSection title="Library" defaultOpen>
      {loadingVolumes && <div className={ui.mutedTextXs}>Loading volumes...</div>}

      {/* volume select + inline refresh */}
      <div className="flex items-center gap-2 w-full">
        <Select
          variant="compact"
          value={selectedVolumeId}
          onChange={(e) => onChangeVolume(e.target.value)}
          className="max-w-[calc(100%-32px)]"
        >
          {volumes.length === 0 && <option value="">No volumes</option>}
          {volumes.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name ?? v.id}
            </option>
          ))}
        </Select>

        <Button type="button" onClick={openCreate} title="Create new volume" variant="icon">
          +
        </Button>

        <Button
          type="button"
          onClick={onRefreshPages}
          disabled={loadingPages || loadingVolumes}
          title="Refresh volumes"
          variant="icon"
          className={loadingPages || loadingVolumes ? ui.button.iconDisabled : undefined}
        >
          R
        </Button>
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        <Button type="button" onClick={handleImport} variant="ghostSmall" disabled={syncing}>
          Import folders
        </Button>
        <Button type="button" onClick={handleDetectMissing} variant="ghostSmall" disabled={syncing}>
          Detect missing
        </Button>
      </div>

      {syncError && <div className={`mt-2 ${ui.warningTextTiny}`}>{syncError}</div>}

      {showCreate && (
        <div className={ui.modalOverlay}>
          <div className={ui.modalPanel}>
            <div className={ui.modalTitle}>Create new volume</div>
            <div className="mt-3 space-y-2">
              <Field label="Name" labelClassName={ui.labelSmall}>
                <input
                  type="text"
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      void handleCreate();
                    }
                  }}
                  className={ui.input}
                  placeholder="My Manga Volume"
                />
              </Field>
              {createError && <div className={ui.warningTextTiny}>{createError}</div>}
            </div>
            <div className={ui.modalActions}>
              <Button type="button" onClick={closeCreate} variant="modalCancel" disabled={creating}>
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handleCreate}
                variant="modalPrimary"
                disabled={creating}
              >
                {creating ? 'Creating...' : 'Create'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {showMissing && (
        <div className={ui.modalOverlay}>
          <div className={ui.modalPanel}>
            <div className={ui.modalTitle}>Missing volumes</div>
            <div className={ui.modalText}>These items are in the DB but missing on disk.</div>
            <ul className={`mt-3 max-h-40 space-y-1 overflow-auto ${ui.listText}`}>
              {missingVolumes.map((volume) => (
                <li key={volume.id}>
                  {volume.name} ({volume.id})
                </li>
              ))}
              {missingPages.map((page) => (
                <li key={`${page.volumeId}-${page.filename}`}>
                  {page.volumeId}/{page.filename}
                </li>
              ))}
            </ul>
            <div className={ui.modalActions}>
              <Button
                type="button"
                onClick={() => setShowMissing(false)}
                variant="modalCancel"
                disabled={syncing}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={handlePruneMissing}
                variant="modalWarning"
                disabled={syncing}
              >
                Remove from DB
              </Button>
            </div>
          </div>
        </div>
      )}
    </CollapsibleSection>
  );
}
