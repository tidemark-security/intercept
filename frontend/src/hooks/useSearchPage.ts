import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { SearchService } from '@/types/generated/services/SearchService';
import type { PaginatedSearchResponse } from '@/types/generated/models/PaginatedSearchResponse';
import type { EntityType } from '@/types/generated/models/EntityType';
import { useSearchCore } from '@/hooks/useSearchCore';
import {
  loadDateRangePreference,
  loadSelectedEntityTypePreference,
  saveDateRangePreference,
  saveSelectedEntityTypePreference,
} from '@/components/search/searchPreferences';
import { isSearchQueryValid } from '@/components/search/searchUtils';

const DEFAULT_PAGE_SIZE = 20;

interface UseSearchPageOptions {
  /** Initial entity type filter (EntityType or 'all') */
  initialEntityType?: EntityType | 'all';
  /** Initial search query */
  initialQuery?: string;
  /** Results per page */
  pageSize?: number;
}

interface UseSearchPageReturn {
  /** Current search query */
  query: string;
  /** Set search query (will be debounced) */
  setQuery: (query: string) => void;
  /** Debounced query value used for API calls */
  debouncedQuery: string;
  /** Current entity type filter ('all' or specific EntityType) */
  entityType: EntityType | 'all';
  /** Set entity type filter */
  setEntityType: (type: EntityType | 'all') => void;
  /** Current page (0-indexed) */
  page: number;
  /** Set current page */
  setPage: (page: number) => void;
  /** Total number of pages */
  totalPages: number;
  /** Total result count */
  totalResults: number;
  /** Query result from TanStack Query */
  queryResult: UseQueryResult<PaginatedSearchResponse, Error>;
  /** Whether search is currently loading */
  isSearching: boolean;
  /** Whether we have results */
  hasResults: boolean;
  /** Clear the search */
  clearSearch: () => void;
  /** Date range filter */
  dateRange: { start: string | null; end: string | null };
  /** Set date range filter */
  setDateRange: (range: { start: string | null; end: string | null }) => void;
  /** Selected tags for server-side OR filtering */
  selectedTags: string[];
  /** Set selected tags for server-side OR filtering */
  setSelectedTags: (tags: string[]) => void;
}

/**
 * Hook for paginated search on the dedicated search page.
 * 
 * Features:
 * - URL query param sync for bookmarkable searches
 * - 300ms debounce to avoid excessive API calls
 * - Minimum 2 character query length
 * - Pagination support
 * - Single entity type filtering
 * 
 * @example
 * ```tsx
 * const { 
 *   query, setQuery, 
 *   entityType, setEntityType,
 *   page, setPage, totalPages,
 *   queryResult, isSearching 
 * } = useSearchPage();
 * ```
 */
export function useSearchPage(
  options: UseSearchPageOptions = {}
): UseSearchPageReturn {
  const {
    initialEntityType = 'all',
    initialQuery = '',
    pageSize = DEFAULT_PAGE_SIZE,
  } = options;

  const [searchParams, setSearchParams] = useSearchParams();
  const sessionEntityType = loadSelectedEntityTypePreference();
  const sessionDateRange = loadDateRangePreference();
  const initialQueryFromUrl = searchParams.get('q') || initialQuery;

  // Initialize state from URL params
  const [entityType, setEntityTypeState] = useState<EntityType | 'all'>(() => {
    const typeParam = searchParams.get('type');
    if (typeParam === 'all' || typeParam === 'alert' || typeParam === 'case' || typeParam === 'task') {
      return typeParam;
    }
    if (initialEntityType !== 'all') {
      return initialEntityType;
    }
    return sessionEntityType;
  });
  const [page, setPageState] = useState(() => {
    const pageParam = searchParams.get('page');
    return pageParam ? Math.max(0, parseInt(pageParam, 10) - 1) : 0;
  });
  const [dateRange, setDateRange] = useState<{ start: string | null; end: string | null }>({
    start: searchParams.get('start') || sessionDateRange?.start || null,
    end: searchParams.get('end') || sessionDateRange?.end || null,
  });
  const [selectedTags, setSelectedTagsState] = useState<string[]>(() =>
    searchParams.getAll('tag').filter((tag) => tag.trim().length > 0)
  );

  const {
    query,
    setQuery: setCoreQuery,
    debouncedQuery,
    isQueryValid,
    isDebouncing,
    clearSearch: clearCoreSearch,
  } = useSearchCore({ initialQuery: initialQueryFromUrl });

  // Sync URL params when state changes
  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedQuery) params.set('q', debouncedQuery);
    if (entityType) params.set('type', entityType);
    if (page > 0) params.set('page', String(page + 1));
    if (dateRange.start) params.set('start', dateRange.start);
    if (dateRange.end) params.set('end', dateRange.end);
    selectedTags.forEach((tag) => params.append('tag', tag));
    
    setSearchParams(params, { replace: true });
  }, [debouncedQuery, entityType, page, dateRange, selectedTags, setSearchParams]);

  // Reset page when entity type changes
  useEffect(() => {
    setPageState(0);
  }, [entityType]);

  // Wrapper for setQuery that resets page
  const setQuery = useCallback((newQuery: string) => {
    setPageState(0);
    setCoreQuery(newQuery);
  }, [setCoreQuery]);

  // Wrapper for setEntityType
  const setEntityType = useCallback((type: EntityType | 'all') => {
    setEntityTypeState(type);
  }, []);

  // Wrapper for setPage
  const setPage = useCallback((newPage: number) => {
    setPageState(newPage);
  }, []);

  const setSelectedTags = useCallback((tags: string[]) => {
    setSelectedTagsState(tags);
    setPageState(0);
  }, []);

  useEffect(() => {
    saveSelectedEntityTypePreference(entityType);
  }, [entityType]);

  useEffect(() => {
    if (!dateRange.start && !dateRange.end) {
      saveDateRangePreference(null);
      return;
    }

    saveDateRangePreference({
      start: dateRange.start || '',
      end: dateRange.end || '',
      preset: 'custom',
    });
  }, [dateRange]);

  // Build the entity type array for API - null/undefined means all types
  const apiEntityTypes = entityType === 'all' ? null : [entityType];
  
  const queryResult = useQuery({
    queryKey: ['unifiedSearch', debouncedQuery, entityType, page, pageSize, dateRange.start, dateRange.end, selectedTags],
    queryFn: () =>
      SearchService.unifiedSearchApiV1SearchGet({
        q: debouncedQuery,
        entityType: apiEntityTypes,
        skip: page * pageSize,
        limit: pageSize,
        startDate: dateRange.start,
        endDate: dateRange.end,
        tags: selectedTags.length > 0 ? selectedTags : null,
      }),
    enabled: isQueryValid,
    staleTime: 30_000, // 30 seconds
    gcTime: 60_000, // 1 minute
    retry: 1,
    placeholderData: (previousData) => previousData, // Keep previous data while loading
  });

  // Only consider results if query is valid - prevents stale results showing after clear
  const totalResults = isQueryValid ? (queryResult.data?.total || 0) : 0;
  const totalPages = Math.ceil(totalResults / pageSize);
  const hasResults = isQueryValid && totalResults > 0;

  const clearSearch = useCallback(() => {
    clearCoreSearch();
    setPageState(0);
  }, [clearCoreSearch]);

  return {
    query,
    setQuery,
    debouncedQuery,
    entityType,
    setEntityType,
    page,
    setPage,
    totalPages,
    totalResults,
    queryResult,
    isSearching: queryResult.isLoading || queryResult.isFetching || isDebouncing,
    hasResults,
    clearSearch,
    dateRange,
    setDateRange,
    selectedTags,
    setSelectedTags,
  };
}

export default useSearchPage;
