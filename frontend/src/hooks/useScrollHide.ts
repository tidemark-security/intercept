import { useEffect, useState, useCallback, RefObject } from 'react';

interface UseScrollHideOptions {
  /** Reference to the scroll container element */
  scrollContainerRef: RefObject<HTMLElement | null>;
  /** Scroll threshold in pixels to trigger hide/show (default: 10) */
  threshold?: number;
  /** Only enable on mobile breakpoint (default: true) */
  mobileOnly?: boolean;
}

/**
 * Hook to hide elements when scrolling down and show them when scrolled back to the top
 * 
 * @param options - Configuration options
 * @returns Object with isVisible state
 */
export function useScrollHide({
  scrollContainerRef,
  threshold = 10,
  mobileOnly = true,
}: UseScrollHideOptions) {
  const [isVisible, setIsVisible] = useState(true);
  const [lastScrollY, setLastScrollY] = useState(0);
  const [isMobile, setIsMobile] = useState(false);

  // Check if we're on mobile
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleScroll = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const currentScrollY = container.scrollTop;

    // If scrolled to top (within threshold), always show
    if (currentScrollY <= threshold) {
      setIsVisible(true);
      setLastScrollY(currentScrollY);
      return;
    }

    // Determine scroll direction
    const scrollingDown = currentScrollY > lastScrollY;

    if (scrollingDown) {
      // Hide when scrolling down
      setIsVisible(false);
    } else if (currentScrollY < lastScrollY - threshold) {
      // Only show when scrolling up significantly (prevents jitter)
      setIsVisible(true);
    }

    setLastScrollY(currentScrollY);
  }, [lastScrollY, threshold, scrollContainerRef]);

  useEffect(() => {
    // Skip if mobileOnly is true and we're not on mobile
    if (mobileOnly && !isMobile) {
      setIsVisible(true);
      return;
    }

    const container = scrollContainerRef.current;
    if (!container) {
      setIsVisible(true);
      return;
    }

    // Set up scroll listener
    container.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, [handleScroll, scrollContainerRef, mobileOnly, isMobile]);

  return { isVisible };
}
