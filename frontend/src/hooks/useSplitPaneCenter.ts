import { useEffect, useState } from 'react';

import type { Breakpoint } from '@/hooks/useBreakpoint';

const DESKTOP_SIDEBAR_WIDTH = 64;
const THREE_COLUMN_HORIZONTAL_PADDING = 32;
const THREE_COLUMN_GAP = 16;
const COLUMN_RAIL_WIDTH = 6;

export const MIN_SPLIT_CENTER_WIDTH = 600;

export function getSplitPaneCenterWidth(viewportWidth: number, leftColumnWidth: number): number {
  return (
    viewportWidth -
    DESKTOP_SIDEBAR_WIDTH -
    THREE_COLUMN_HORIZONTAL_PADDING -
    (THREE_COLUMN_GAP * 2) -
    COLUMN_RAIL_WIDTH -
    leftColumnWidth
  );
}

export function canShowSplitPaneCenter(
  viewportWidth: number,
  leftColumnWidth: number,
  breakpoint: Breakpoint,
): boolean {
  return breakpoint !== 'mobile' && getSplitPaneCenterWidth(viewportWidth, leftColumnWidth) >= MIN_SPLIT_CENTER_WIDTH;
}

export function useViewportWidth(): number {
  const [viewportWidth, setViewportWidth] = useState(() =>
    typeof window === 'undefined' ? 0 : window.innerWidth,
  );

  useEffect(() => {
    const handleResize = () => setViewportWidth(window.innerWidth);

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return viewportWidth;
}

