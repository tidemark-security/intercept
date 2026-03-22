/**
 * Column configuration utilities for three-column layout
 */

import type { ColumnConfig, VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import type { Breakpoint } from '@/hooks/useBreakpoint';
import { getBreakpoint } from '@/hooks/useBreakpoint';

/**
 * Compute initial visible columns based on breakpoint
 * Used to avoid flash on initial page load by computing correct initial state
 */
export function getInitialVisibleColumns(): VisibleColumns {
  if (typeof window === 'undefined') return 'left';
  const breakpoint = getBreakpoint(window.innerWidth);
  // On ultrawide, show left+center to display the empty state placeholder
  // On other breakpoints, show only left
  return breakpoint === 'ultrawide' ? 'left+center' : 'left';
}

/**
 * Generate column configuration for responsive layout
 * Handles the common pattern where desktop/tablet/ultrawide share config
 */
export function getColumnConfig(selectedAlertId: number | null): ColumnConfig {
  const fixedListWidth = 'w-[768px] shrink-0';
  const fullWidth = 'w-full';
  const centerWidth = 'flex-1';
  const rightWidth = 'w-[512px] shrink-0';

  // Config for desktop/tablet where we want full width list when no alert is selected
  const standardConfig = {
    leftWidth: selectedAlertId ? fixedListWidth : fullWidth,
    centerWidth,
    rightWidth,
  };

  // Config for ultrawide where we always want fixed width list (to show placeholder in center)
  const ultrawideConfig = {
    leftWidth: fixedListWidth,
    centerWidth,
    rightWidth,
  };

  return {
    ultrawide: ultrawideConfig,
    desktop: standardConfig,
    tablet: standardConfig,
    mobile: {
      leftWidth: 'w-full',
      centerWidth: 'w-full',
      rightWidth: 'w-full',
    },
  };
}
