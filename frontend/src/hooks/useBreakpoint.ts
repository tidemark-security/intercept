/**
 * Custom hook for reactive breakpoint detection
 * Provides current breakpoint state that updates on window resize
 */

import { useState, useEffect } from 'react';

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
 * Hook that provides reactive current breakpoint
 * Automatically updates on window resize
 */
export function useBreakpoint(): Breakpoint {
  const [breakpoint, setBreakpoint] = useState<Breakpoint>(() =>
    getBreakpoint(window.innerWidth)
  );

  useEffect(() => {
    const handleResize = () => {
      const newBreakpoint = getBreakpoint(window.innerWidth);
      setBreakpoint(newBreakpoint);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return breakpoint;
}
