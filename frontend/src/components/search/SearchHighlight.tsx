/**
 * SearchHighlight - Shared highlight styling for search matches
 * 
 * Provides consistent highlight styling across text snippets and timeline cards.
 * Change the className here to update highlight styling everywhere.
 */

import React from 'react';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';

/** Tailwind classes for search match highlighting */
export const SEARCH_HIGHLIGHT_DARK_CLASSES = 'bg-accent-1-200 text-accent-1-1000 font-medium rounded px-0.5';
export const SEARCH_HIGHLIGHT_LIGHT_CLASSES = 'bg-accent-1-300 text-accent-1-1100 font-semibold rounded px-0.5';

interface SearchHighlightProps {
  children: React.ReactNode;
}

/**
 * Wrapper component for highlighted search matches
 */
export function SearchHighlight({ children }: SearchHighlightProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  return (
    <span
      className={cn(
        isDarkTheme ? SEARCH_HIGHLIGHT_DARK_CLASSES : SEARCH_HIGHLIGHT_LIGHT_CLASSES
      )}
    >
      {children}
    </span>
  );
}

export default SearchHighlight;
