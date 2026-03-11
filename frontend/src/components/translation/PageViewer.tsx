// src/components/translation/PageViewer.tsx

import type { Box, BoxType } from '../../types';
import { ui } from '../../ui/tokens';
import { EDITABLE_BOX_TYPES } from '../../utils/boxes';
import { PageCanvas } from './PageCanvas';

interface PageViewerProps {
  imageUrl: string | null;
  loadingPages: boolean;
  error: string | null;
  pageIndex: number;
  pageCount: number;
  currentPageFilename: string;
  isDraftPage?: boolean;
  boxesByType: Record<BoxType, Box[]>;
  visibleBoxTypes: BoxType[];
  activeBoxType: BoxType;
  onChangeBoxesForType: (type: BoxType, next: Box[]) => void;
  onToggleVisibleBoxType: (type: BoxType) => void;
  onChangeActiveBoxType: (type: BoxType) => void;
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
  emptyTitle?: string;
  emptySubtitle?: string;
}

/**
 * High-level page wrapper:
 * - Shows loading/error/empty states
 * - Centers the PageCanvas
 */
export function PageViewer({
  imageUrl,
  loadingPages,
  error,
  pageIndex,
  pageCount,
  currentPageFilename,
  isDraftPage = false,
  boxesByType,
  visibleBoxTypes,
  activeBoxType,
  onChangeBoxesForType,
  onToggleVisibleBoxType,
  onChangeActiveBoxType,
  hasPrev,
  hasNext,
  onPrev,
  onNext,
  emptyTitle,
  emptySubtitle,
}: PageViewerProps) {
  const showError = !!error;
  const showLoading = !error && loadingPages;
  const showCanvas = !error && !loadingPages;
  const pageLabel = isDraftPage
    ? 'Draft page'
    : pageCount > 0
      ? `Page ${pageIndex + 1} / ${pageCount}`
      : 'No page selected';
  const filenameLabel = isDraftPage
    ? currentPageFilename || 'unsaved'
    : currentPageFilename || 'unknown';

  return (
    <div className={ui.viewerWrap}>
      {showError && <div className={`m-auto px-4 ${ui.errorText}`}>{error}</div>}

      {showLoading && <div className={`m-auto ${ui.mutedTextSm}`}>Loading page...</div>}

      {showCanvas && (
        <div className={ui.viewerCenter}>
          <PageCanvas
            imageUrl={imageUrl}
            pageLabel={pageLabel}
            filenameLabel={filenameLabel}
            boxesByType={boxesByType}
            visibleBoxTypes={visibleBoxTypes}
            activeBoxType={activeBoxType}
            editableBoxTypes={EDITABLE_BOX_TYPES}
            onChangeBoxesForType={onChangeBoxesForType}
            onToggleVisibleBoxType={onToggleVisibleBoxType}
            onChangeActiveBoxType={onChangeActiveBoxType}
            hasPrev={hasPrev}
            hasNext={hasNext}
            onPrev={onPrev}
            onNext={onNext}
            emptyTitle={emptyTitle}
            emptySubtitle={emptySubtitle}
          />
        </div>
      )}
    </div>
  );
}
