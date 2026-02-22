/**
 * Custom hook for auto-scrolling to an element with retry logic
 * Useful when element may not be in DOM immediately
 */

import { useEffect } from 'react';

interface UseAutoScrollOptions {
  /** ID of the element to scroll to (without any prefix) */
  elementId: string | null;
  /** Prefix to add to element ID for DOM lookup */
  idPrefix?: string;
  /** Maximum number of retry attempts */
  maxAttempts?: number;
  /** Delay between retry attempts in milliseconds */
  retryDelay?: number;
  /** Initial delay before first attempt in milliseconds */
  initialDelay?: number;
  /** Callback when scroll completes */
  onScrollComplete?: () => void;
  /** Callback when scroll fails after all retries */
  onScrollFailed?: (elementId: string) => void;
  /** Dependencies that should trigger scroll (e.g., data loaded) */
  enabled?: boolean;
}

/**
 * Hook that automatically scrolls to an element by ID with retry logic
 * Handles cases where DOM may not be ready immediately
 */
export function useAutoScroll({
  elementId,
  idPrefix = '',
  maxAttempts = 10,
  retryDelay = 100,
  initialDelay = 100,
  onScrollComplete,
  onScrollFailed,
  enabled = true,
}: UseAutoScrollOptions) {
  useEffect(() => {
    if (!elementId || !enabled) return;

    let attempts = 0;
    let timeoutId: NodeJS.Timeout;

    const tryScroll = () => {
      const fullId = `${idPrefix}${elementId}`;
      const element = document.getElementById(fullId);
      
      if (element) {
        console.log('Scrolling to element:', fullId);
        element.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
          inline: 'nearest',
        });
        onScrollComplete?.();
      } else {
        attempts++;
        if (attempts < maxAttempts) {
          console.log(`Retry scroll attempt ${attempts}/${maxAttempts} for:`, fullId);
          timeoutId = setTimeout(tryScroll, retryDelay);
        } else {
          console.warn('Failed to find element after', maxAttempts, 'attempts:', fullId);
          onScrollFailed?.(elementId);
        }
      }
    };

    // Initial delay to let React render
    timeoutId = setTimeout(tryScroll, initialDelay);

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [elementId, idPrefix, maxAttempts, retryDelay, initialDelay, onScrollComplete, onScrollFailed, enabled]);
}
