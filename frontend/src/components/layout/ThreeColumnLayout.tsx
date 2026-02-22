import React, { useState, useEffect } from 'react';
import type { ThreeColumnLayoutProps, Breakpoint, VisibleColumns } from './ThreeColumnLayout.types';
import { ColumnRail, DEFAULT_WIDTH } from './ColumnRail';

/**
 * Hook to detect current breakpoint based on window width
 */
function useBreakpoint(): Breakpoint {
  const getBreakpoint = (width: number): Breakpoint => {
    if (width >= 1920) return 'ultrawide';
    if (width >= 1024) return 'desktop';
    if (width >= 768) return 'tablet';
    return 'mobile';
  };

  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() => 
    typeof window !== 'undefined' ? getBreakpoint(window.innerWidth) : 'desktop'
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleResize = () => {
      setBreakpoint(getBreakpoint(window.innerWidth));
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return breakpoint;
}

/**
 * ThreeColumnLayout - Reusable responsive three-column layout component
 * 
 * Manages responsive behavior across different breakpoints:
 * - Ultrawide (≥1920px): Right column floats as drawer when visible
 * - Desktop (1024px-1919px): Right column floats as drawer when visible
 * - Tablet (768px-1023px): Right column floats as drawer when visible
 * - Mobile (<768px): Shows single column (no floating)
 * 
 * The actual visibility is controlled by the `visibleColumns` prop, allowing
 * full flexibility regardless of breakpoint.
 * 
 * @example
 * ```tsx
 * <ThreeColumnLayout
 *   leftColumn={<AlertList {...} />}
 *   centerColumn={<AlertTimeline {...} />}
 *   rightColumn={<RightDock {...} />}
 *   visibleColumns={visibleColumns}
 *   onVisibleColumnsChange={setVisibleColumns}
 * />
 * ```
 */
export function ThreeColumnLayout({
  leftColumn,
  centerColumn,
  rightColumn,
  visibleColumns,
  onVisibleColumnsChange,
  className = '',
  columnConfig,
  dimLeftColumn = false,
  showLeftRail = false,
  leftRailCollapsed = false,
  onLeftRailToggle,
  leftColumnWidth,
  onLeftColumnWidthChange,
}: ThreeColumnLayoutProps) {
  const breakpoint = useBreakpoint();

  // Development mode validation
  if (process.env.NODE_ENV === 'development') {
    const validValues: VisibleColumns[] = ['left', 'center', 'right', 'left+center', 'center+right', 'all'];
    if (!validValues.includes(visibleColumns)) {
      console.warn(
        `[ThreeColumnLayout] Invalid visibleColumns: "${visibleColumns}". Must be one of: ${validValues.join(', ')}`
      );
    }
  }

  // Default column widths for each breakpoint
  const ultrawideLeftWidth = columnConfig?.ultrawide?.leftWidth || 'max-w-[768px]';
  const ultrawideCenterWidth = columnConfig?.ultrawide?.centerWidth || 'grow';
  const ultrawideRightWidth = columnConfig?.ultrawide?.rightWidth || 'w-[400px]';

  const desktopLeftWidth = columnConfig?.desktop?.leftWidth || 'max-w-[768px]';
  const desktopCenterWidth = columnConfig?.desktop?.centerWidth || 'grow';
  const desktopRightWidth = columnConfig?.desktop?.rightWidth || 'w-[400px]';

  const tabletLeftWidth = columnConfig?.tablet?.leftWidth || 'max-w-[768px]';
  const tabletCenterWidth = columnConfig?.tablet?.centerWidth || 'grow';
  const tabletRightWidth = columnConfig?.tablet?.rightWidth || 'w-[400px]';

  const mobileLeftWidth = columnConfig?.mobile?.leftWidth || 'w-full';
  const mobileCenterWidth = columnConfig?.mobile?.centerWidth || 'w-full';
  const mobileRightWidth = columnConfig?.mobile?.rightWidth || 'w-full';

  // Determine visibility for each column based on visibleColumns prop
  const showLeft = visibleColumns === 'left' || visibleColumns === 'left+center' || visibleColumns === 'all';
  const showCenter = visibleColumns === 'center' || visibleColumns === 'left+center' || visibleColumns === 'center+right' || visibleColumns === 'all';
  const showRight = visibleColumns === 'right' || visibleColumns === 'center+right' || visibleColumns === 'all';

  // Use custom width from props when rail is enabled and we have a width
  const getLeftWidthStyle = () => {
    if (showLeftRail && leftColumnWidth && breakpoint !== 'mobile') {
      return { width: `${leftColumnWidth}px`, flexShrink: 0 };
    }
    return undefined;
  };

  // Determine if we should show the rail (only when both columns visible and rail is enabled)
  const shouldShowRail = showLeftRail && showLeft && showCenter && breakpoint !== 'mobile';

  return (
    <div className={`relative flex h-full w-full items-start gap-4 px-4 py-4 mobile:px-0 mobile:py-0 ${className}`}>
      {/* Left Column */}
      {showLeft && (
        <div
          className={`flex flex-col items-start self-stretch bg-default-background transition-all duration-300 ease-in-out ${
            // Only apply Tailwind width classes when not using custom pixel width
            !showLeftRail || !leftColumnWidth ? (
              breakpoint === 'ultrawide' ? ultrawideLeftWidth :
              breakpoint === 'desktop' ? desktopLeftWidth :
              breakpoint === 'tablet' ? tabletLeftWidth :
              mobileLeftWidth
            ) : 'shrink-0'
          } ${showCenter && dimLeftColumn ? 'brightness-75 hover:brightness-100' : ''} ${breakpoint !== 'mobile' ? 'bevel-tr-3xl' : ''}`}
          style={{
            ...getLeftWidthStyle(),
          }}
        >
          {leftColumn}
        </div>
      )}

      {/* Column Rail - Toggle/Resize handle between left and center */}
      {shouldShowRail && onLeftRailToggle && (
        <ColumnRail
          collapsed={leftRailCollapsed}
          onToggle={onLeftRailToggle}
          width={leftColumnWidth ?? DEFAULT_WIDTH}
          onWidthChange={onLeftColumnWidthChange}
          resizable={!!onLeftColumnWidthChange}
        />
      )}

      {/* Center Column */}
      {showCenter && (
        <div
          className={`flex flex-col items-start self-stretch bg-default-background transition-all duration-300 ease-in-out ${
            breakpoint === 'ultrawide' ? ultrawideCenterWidth :
            breakpoint === 'desktop' ? desktopCenterWidth :
            breakpoint === 'tablet' ? tabletCenterWidth :
            mobileCenterWidth
          } ${breakpoint !== 'mobile' ? 'bevel-tr-3xl' : ''}`}
        >
          {centerColumn}
        </div>
      )}

      {/* Right Column - Floats as drawer on all breakpoints except mobile */}
      {showRight && (
        <div
          className={`
            bg-neutral-50 p-6 transition-all duration-300 ease-in-out
            ${
              // Ultrawide: Float as drawer when visible
              breakpoint === 'ultrawide' 
                ? `absolute right-0 top-0 bottom-0 ${ultrawideRightWidth} z-10 max-h-screen overflow-y-auto shadow-lg animate-slide-in-right` 
                : ''
            }
            ${
              // Desktop: Float as drawer when visible
              breakpoint === 'desktop'
                ? `absolute right-0 top-0 bottom-0 ${desktopRightWidth} z-10 max-h-screen overflow-y-auto shadow-lg animate-slide-in-right`
                : ''
            }
            ${
              // Tablet: Float as drawer when visible
              breakpoint === 'tablet'
                ? `absolute right-0 top-0 bottom-0 ${tabletRightWidth} z-10 max-h-screen overflow-y-auto shadow-lg animate-slide-in-right`
                : ''
            }
            ${
              // Mobile: Always relative (normal flow, doesn't float to avoid covering bottom nav)
              breakpoint === 'mobile'
                ? `relative h-full ${mobileRightWidth} p-4 content-fade-in`
                : ''
            }
          `}
        >
          {rightColumn}
        </div>
      )}
    </div>
  );
}