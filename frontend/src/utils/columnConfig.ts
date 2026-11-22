/**
 * Column configuration utilities for three-column layout
 */

import type { ColumnConfig } from '@/components/layout/ThreeColumnLayout.types';

/**
 * Generate column configuration for responsive layout
 * Handles the common pattern where desktop/tablet/ultrawide share config
 */
export function getColumnConfig(_selectedEntityId: number | null, listWidth?: number, expandLeft = false): ColumnConfig {
  const fixedListWidth = expandLeft ? 'w-full' : listWidth ? 'shrink-0' : 'w-[768px] shrink-0';
  const centerWidth = 'flex-1';
  const rightWidth = 'w-[512px] shrink-0';

  // Keep list width fixed even when no entity is selected so list/detail resize
  // works while the center placeholder is showing.
  const standardConfig = {
    leftWidth: fixedListWidth,
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
