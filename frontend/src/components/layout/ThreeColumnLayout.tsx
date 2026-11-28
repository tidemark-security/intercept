import { useCallback, useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { ThreeColumnLayout as UxThreeColumnLayout } from '@tidemark-security/ux';
import { getBreakpoint } from '@/hooks/useBreakpoint';
import { canShowSplitPaneCenter, getSplitPaneCenterWidth, MIN_SPLIT_CENTER_WIDTH, useViewportWidth } from '@/hooks/useSplitPaneCenter';
import { cn } from '@/utils/cn';
import { SplitResizeHandle } from './SplitResizeHandle';
import type { ColumnConfig, FloatingPane, ThreeColumnLayoutProps } from './ThreeColumnLayout.types';
import styles from './ThreeColumnLayout.module.css';
import floatingStyles from './FloatingPanes.module.css';

const MIN_LEFT_WIDTH = 320;
const MAX_LEFT_WIDTH = 800;
const HOVER_ACTIVATION_DELAY_MS = 1000;
// Match UX's storage key so list and assistant panel widths carry over.
const DEFAULT_WIDTH_KEY = 'intercept-ai-pane-width';
const ignoreColumnChange = () => {};

function getWideSplitConfig(config: ColumnConfig | undefined): ColumnConfig {
  const columns = { leftWidth: styles.left, centerWidth: styles.center };
  return {
    ...config,
    tablet: { ...config?.tablet, ...columns },
    desktop: { ...config?.desktop, ...columns },
    ultrawide: { ...config?.ultrawide, ...columns },
  };
}

function getFloatingConfig(config: ColumnConfig | undefined, hasDock: boolean): ColumnConfig {
  const applyLayer = (base: ColumnConfig["tablet"]) => ({
    ...base,
    leftWidth: hasDock ? floatingStyles.leftBehindDock : floatingStyles.leftLayer,
    centerWidth: hasDock ? base?.centerWidth : floatingStyles.centerLayer,
  });
  return {
    ...config,
    tablet: applyLayer(config?.tablet),
    desktop: applyLayer(config?.desktop),
    ultrawide: applyLayer(config?.ultrawide),
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
  onVisibleColumnsChange = ignoreColumnChange,
  floatingPanes,
  ...props
}: ThreeColumnLayoutProps) {
  const layoutRef = useRef<HTMLDivElement>(null);
  const paneId = useId();
  const viewportWidth = useViewportWidth();
  const breakpoint = getBreakpoint(viewportWidth);
  const [activePane, setActivePane] = useState<FloatingPane>("center");
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelPendingHover = useCallback(() => {
    if (hoverTimer.current !== null) clearTimeout(hoverTimer.current);
    hoverTimer.current = null;
  }, []);
  const maxWidth = Math.min(MAX_LEFT_WIDTH, getSplitPaneCenterWidth(viewportWidth, 0) - MIN_SPLIT_CENTER_WIDTH);
  const bothPanesVisible = props.visibleColumns === 'left+center' || props.visibleColumns === 'all';
  const overlap = bothPanesVisible && breakpoint !== "mobile" && (
    floatingPanes?.mode === "on" ||
    (floatingPanes?.mode === "narrow" &&
      !canShowSplitPaneCenter(viewportWidth, leftColumnWidth ?? MIN_LEFT_WIDTH, breakpoint))
  );
  const hasDock = props.visibleColumns === "all";
  const floating = overlap && !hasDock;
  const frontPane = floatingPanes?.frontPane ?? activePane;
  const wideSplit = !overlap && showLeftRail && !leftRailCollapsed && bothPanesVisible && maxWidth >= MIN_LEFT_WIDTH
    && leftColumnWidth !== undefined && !!onLeftColumnWidthChange;
  const width = Math.min(maxWidth, Math.max(MIN_LEFT_WIDTH, leftColumnWidth ?? MIN_LEFT_WIDTH));
  const legacyWidthChange = onLeftColumnWidthChange && leftColumnWidthStorageKey !== DEFAULT_WIDTH_KEY
    ? (nextWidth: number) => {
      onLeftColumnWidthChange(nextWidth);
      saveWidth(leftColumnWidthStorageKey, nextWidth);
    }
    : onLeftColumnWidthChange;

  useEffect(() => {
    if (!floating) setActivePane("center");
  }, [floating]);
  useEffect(() => cancelPendingHover, [cancelPendingHover, floating, frontPane]);

  function renderPane(pane: FloatingPane, content: ReactNode) {
    if (!floatingPanes) return content;
    const background = floating && pane !== frontPane && (pane === "left" || !floatingPanes.centerPlaceholder);
    const activate = floatingPanes.onFrontPaneChange ?? setActivePane;
    const label = floatingPanes.labels[pane];
    return (
      <div
        ref={floatingPanes.refs?.[pane]}
        className={floating ? "relative flex h-full min-h-0 w-full flex-col items-start focus:outline-none" : "contents"}
        role={floating ? "region" : undefined}
        aria-label={floating ? label : undefined}
        tabIndex={floating ? -1 : undefined}
      >
        <div className="contents" inert={background || undefined} aria-hidden={background || undefined}>{content}</div>
        {background && (
          <button
            type="button"
            aria-label={`Bring ${label} to front`}
            title={`Bring ${label} to front`}
            className="absolute inset-0 cursor-pointer bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus-border"
            onPointerEnter={(event) => {
              if (event.pointerType !== "mouse") return;
              cancelPendingHover();
              const button = event.currentTarget;
              hoverTimer.current = setTimeout(() => {
                hoverTimer.current = null;
                if (button.isConnected) activate(pane);
              }, HOVER_ACTIVATION_DELAY_MS);
            }}
            onPointerLeave={cancelPendingHover}
            onPointerCancel={cancelPendingHover}
            onClick={(event) => {
              cancelPendingHover();
              activate(pane);
              // The activation button disappears as the pane comes forward.
              event.currentTarget.parentElement?.focus({ preventScroll: true });
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div
      ref={layoutRef}
      className="contents"
      style={wideSplit ? { '--split-left-width': `${width}px` } as CSSProperties : undefined}
    >
      <UxThreeColumnLayout
        {...props}
        onVisibleColumnsChange={onVisibleColumnsChange}
        className={cn(
          className,
          wideSplit && styles.split,
          floating && floatingStyles.overlap,
          floating && frontPane === "left" && floatingStyles.leftInFront,
          floating && floatingPanes?.centerPlaceholder && floatingStyles.placeholder,
        )}
        columnConfig={overlap ? getFloatingConfig(columnConfig, hasDock) : wideSplit ? getWideSplitConfig(columnConfig) : columnConfig}
        showLeftRail={showLeftRail && !wideSplit && !overlap}
        dimLeftColumn={!overlap && props.dimLeftColumn}
        leftRailCollapsed={leftRailCollapsed}
        onLeftRailToggle={onLeftRailToggle}
        leftColumnWidth={leftColumnWidth}
        onLeftColumnWidthChange={legacyWidthChange}
        leftColumn={<div className="contents" id={paneId}>{renderPane("left", leftColumn)}</div>}
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
            {renderPane("center", centerColumn)}
          </>
        )}
      />
    </div>
  );
}
