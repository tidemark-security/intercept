import { useState, useEffect, useCallback } from 'react';
import { isSearchQueryValid, MIN_SEARCH_QUERY_LENGTH } from '@/components/search/searchUtils';

const DEFAULT_DEBOUNCE_MS = 300;

interface UseSearchCoreOptions {
  initialQuery?: string;
  debounceMs?: number;
}

interface UseSearchCoreReturn {
  query: string;
  setQuery: (query: string) => void;
  debouncedQuery: string;
  isQueryValid: boolean;
  isNoContentMode: boolean;
  isDebouncing: boolean;
  clearSearch: () => void;
}

export function useSearchCore(options: UseSearchCoreOptions = {}): UseSearchCoreReturn {
  const {
    initialQuery = '',
    debounceMs = DEFAULT_DEBOUNCE_MS,
  } = options;

  const [query, setQuery] = useState(initialQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(initialQuery);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(query);
    }, debounceMs);

    return () => clearTimeout(timer);
  }, [query, debounceMs]);

  const clearSearch = useCallback(() => {
    setQuery('');
    setDebouncedQuery('');
  }, []);

  const isNoContentMode = debouncedQuery.trim() === '*';
  const isQueryValid = isSearchQueryValid(debouncedQuery);
  const isDebouncing = query !== debouncedQuery && (query.length >= MIN_SEARCH_QUERY_LENGTH || query.trim() === '*');

  return {
    query,
    setQuery,
    debouncedQuery,
    isQueryValid,
    isNoContentMode,
    isDebouncing,
    clearSearch,
  };
}

export default useSearchCore;
