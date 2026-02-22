/**
 * Custom hook for managing column navigation in three-column layout
 * Provides helpers for responsive column switching, especially on mobile
 */

import { useCallback } from 'react';
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { useBreakpoint } from './useBreakpoint';

export interface UseColumnNavigationReturn {
  /** Current breakpoint */
  breakpoint: ReturnType<typeof useBreakpoint>;
  
  /** Switch to specified column on mobile only */
  switchToColumnOnMobile: (column: 'left' | 'center' | 'right') => void;
  
  /** Check if currently on mobile breakpoint */
  isMobile: boolean;
}

/**
 * Hook for managing column navigation with mobile-specific behavior
 * 
 * @param setVisibleColumns Callback to update visible columns
 * @returns Navigation helpers and breakpoint info
 */
export function useColumnNavigation(
  setVisibleColumns: (columns: VisibleColumns) => void
): UseColumnNavigationReturn {
  const breakpoint = useBreakpoint();
  const isMobile = breakpoint === 'mobile';

  const switchToColumnOnMobile = useCallback(
    (column: 'left' | 'center' | 'right') => {
      if (isMobile) {
        setVisibleColumns(column);
      }
    },
    [isMobile, setVisibleColumns]
  );

  return {
    breakpoint,
    switchToColumnOnMobile,
    isMobile,
  };
}
