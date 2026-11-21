import { useId, useRef, type CSSProperties } from 'react';
import { ThreeColumnLayout as UxThreeColumnLayout } from '@tidemark-security/ux';
import { getSplitPaneCenterWidth, MIN_SPLIT_CENTER_WIDTH, useViewportWidth } from '@/hooks/useSplitPaneCenter';
import { cn } from '@/utils/cn';
import { SplitResizeHandle } from './SplitResizeHandle';
import type { ColumnConfig, ThreeColumnLayoutProps } from './ThreeColumnLayout.types';
import styles from './ThreeColumnLayout.module.css';

const MIN_LEFT_WIDTH = 320;
const MAX_LEFT_WIDTH = 800;
// Match UX's storage key so list and assistant panel widths carry over.
const DEFAULT_WIDTH_KEY = 'intercept-ai-pane-width';

function getWideSplitConfig(config: ColumnConfig | undefined): ColumnConfig {
  const columns = { leftWidth: styles.left, centerWidth: styles.center };
  return {
    ...config,
    tablet: { ...config?.tablet, ...columns },
    desktop: { ...config?.desktop, ...columns },
    ultrawide: { ...config?.ultrawide, ...columns },
  };
}

function saveWidth(key: string, width: number) {
  try {
    localStorage.setItem(key, String(width));
  } catch {
    // Resizing still works when local storage is unavailable.
  }
}

export function ThreeColumnLayout({
  className,
  columnConfig,
  leftColumn,
  centerColumn,
  showLeftRail,
  leftRailCollapsed,
  onLeftRailToggle,
  leftColumnWidth,
  onLeftColumnWidthChange,
  leftRailLabel = 'Resize left pane',
  leftColumnWidthStorageKey = DEFAULT_WIDTH_KEY,
  ...props
}: ThreeColumnLayoutProps) {
  const layoutRef = useRef<HTMLDivElement>(null);
  const paneId = useId();
  const viewportWidth = useViewportWidth();
  const maxWidth = Math.min(MAX_LEFT_WIDTH, getSplitPaneCenterWidth(viewportWidth, 0) - MIN_SPLIT_CENTER_WIDTH);
  const bothPanesVisible = props.visibleColumns === 'left+center' || props.visibleColumns === 'all';
  const wideSplit = showLeftRail && !leftRailCollapsed && bothPanesVisible && maxWidth >= MIN_LEFT_WIDTH
    && leftColumnWidth !== undefined && !!onLeftColumnWidthChange;
  const width = Math.min(maxWidth, Math.max(MIN_LEFT_WIDTH, leftColumnWidth ?? MIN_LEFT_WIDTH));
  const legacyWidthChange = onLeftColumnWidthChange && leftColumnWidthStorageKey !== DEFAULT_WIDTH_KEY
    ? (nextWidth: number) => {
      onLeftColumnWidthChange(nextWidth);
      saveWidth(leftColumnWidthStorageKey, nextWidth);
    }
    : onLeftColumnWidthChange;

  return (
    <div
      ref={layoutRef}
      className="contents"
      style={wideSplit ? { '--split-left-width': `${width}px` } as CSSProperties : undefined}
    >
      <UxThreeColumnLayout
        {...props}
        className={cn(className, wideSplit && styles.split)}
        columnConfig={wideSplit ? getWideSplitConfig(columnConfig) : columnConfig}
        showLeftRail={showLeftRail && !wideSplit}
        leftRailCollapsed={leftRailCollapsed}
        onLeftRailToggle={onLeftRailToggle}
        leftColumnWidth={leftColumnWidth}
        onLeftColumnWidthChange={legacyWidthChange}
        leftColumn={<div className="contents" id={paneId}>{leftColumn}</div>}
        centerColumn={(
          <>
            {wideSplit && (
              <SplitResizeHandle
                label={leftRailLabel}
                paneId={paneId}
                layoutRef={layoutRef}
                width={width}
                minWidth={MIN_LEFT_WIDTH}
                maxWidth={maxWidth}
                onCollapse={onLeftRailToggle}
                onWidthCommit={(nextWidth) => {
                  if (nextWidth === leftColumnWidth) return;
                  onLeftColumnWidthChange?.(nextWidth);
                  saveWidth(leftColumnWidthStorageKey, nextWidth);
                }}
              />
            )}
            {centerColumn}
          </>
        )}
      />
    </div>
  );
}
