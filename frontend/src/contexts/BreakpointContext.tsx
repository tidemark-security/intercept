/**
 * Breakpoint Context - Provides reactive breakpoint state at the app level
 * 
 * By calculating the breakpoint once at the app root, all child components
 * have immediate access to the current breakpoint without re-calculating
 * or waiting for effects to run.
 */

/* eslint-disable react-refresh/only-export-components */

import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';

export type Breakpoint = 'mobile' | 'tablet' | 'desktop' | 'ultrawide';

/**
 * Get current breakpoint based on window width
 * - mobile: < 768px
 * - tablet: 768px - 1023px
 * - desktop: 1024px - 1919px
 * - ultrawide: >= 1920px
 */
export function getBreakpoint(width: number): Breakpoint {
  if (width >= 1920) return 'ultrawide';
  if (width >= 1024) return 'desktop';
  if (width >= 768) return 'tablet';
  return 'mobile';
}

/**
 * Get initial visible columns based on breakpoint
 * Used to prevent layout flash on page load
 */
export function getInitialVisibleColumns(breakpoint: Breakpoint, dockOpen: boolean = false): VisibleColumns {
  switch (breakpoint) {
    case 'ultrawide':
      return dockOpen ? 'all' : 'left+center';
    case 'desktop':
    case 'tablet':
      return dockOpen ? 'all' : 'left+center';
    case 'mobile':
      return 'center';
  }
}

interface BreakpointContextValue {
  breakpoint: Breakpoint;
  isMobile: boolean;
  isTablet: boolean;
  isDesktop: boolean;
  isUltrawide: boolean;
  getInitialVisibleColumns: (dockOpen?: boolean) => VisibleColumns;
}

const BreakpointContext = createContext<BreakpointContextValue | null>(null);

/**
 * Provider component that calculates breakpoint once at app level
 */
export function BreakpointProvider({ children }: { children: React.ReactNode }) {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() =>
    typeof window !== 'undefined' ? getBreakpoint(window.innerWidth) : 'desktop'
  );

  useEffect(() => {
    const handleResize = () => {
      const newBreakpoint = getBreakpoint(window.innerWidth);
      setBreakpoint(newBreakpoint);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const value = useMemo<BreakpointContextValue>(() => ({
    breakpoint,
    isMobile: breakpoint === 'mobile',
    isTablet: breakpoint === 'tablet',
    isDesktop: breakpoint === 'desktop',
    isUltrawide: breakpoint === 'ultrawide',
    getInitialVisibleColumns: (dockOpen = false) => getInitialVisibleColumns(breakpoint, dockOpen),
  }), [breakpoint]);

  return (
    <BreakpointContext.Provider value={value}>
      {children}
    </BreakpointContext.Provider>
  );
}

/**
 * Hook to access breakpoint context
 * Must be used within a BreakpointProvider
 */
export function useBreakpointContext(): BreakpointContextValue {
  const context = useContext(BreakpointContext);
  if (!context) {
    throw new Error('useBreakpointContext must be used within a BreakpointProvider');
  }
  return context;
}
