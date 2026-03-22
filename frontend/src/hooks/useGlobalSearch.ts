import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { useMemo } from 'react';
import { SearchService } from '@/types/generated/services/SearchService';
import type { PaginatedSearchResponse } from '@/types/generated/models/PaginatedSearchResponse';
import type { EntityType } from '@/types/generated/models/EntityType';
import { useSearchCore } from '@/hooks/useSearchCore';

const DEFAULT_LIMIT = 10;

interface UseGlobalSearchOptions {
  /** Filter by entity types. Default: all types */
  entityTypes?: EntityType[] | null;
  /** Start of date range (ISO8601). Default: 30 days ago */
  startDate?: string | null;
  /** End of date range (ISO8601). Default: now */
  endDate?: string | null;
  /** Maximum results to return (1-100). Default: 10 */
  limit?: number;
  /** Enable/disable the query */
  enabled?: boolean;
  /** Tag filters (OR semantics) */
  tags?: string[] | null;
}

interface UseGlobalSearchReturn {
  /** Current search query */
  query: string;
  /** Set search query (will be debounced) */
  setQuery: (query: string) => void;
  /** Debounced query value used for API calls */
  debouncedQuery: string;
  /** Query result from TanStack Query */
  queryResult: UseQueryResult<PaginatedSearchResponse, Error>;
  /** Whether search is currently loading */
  isSearching: boolean;
  /** Whether we have results */
  hasResults: boolean;
  /** Search results (flat list, ranked by score) */
  results: PaginatedSearchResponse['results'];
  /** Total count of matching results */
  total: number;
  /** Clear the search */
  clearSearch: () => void;
}

/**
 * Hook for unified global search across alerts, cases, and tasks.
 * 
 * Features:
 * - 300ms debounce to avoid excessive API calls
 * - Minimum 2 character query length
 * - Results ranked by score (flat list, not grouped)
 * - Fuzzy fallback when exact match fails
 * 
 * @example
 * ```tsx
 * const { query, setQuery, queryResult, results, isSearching } = useGlobalSearch();
 * 
 * return (
 *   <input 
 *     value={query} 
 *     onChange={(e) => setQuery(e.target.value)} 
 *     placeholder="Search alerts, cases, tasks..."
 *   />
 *   {isSearching && <Spinner />}
 *   {results.map(item => <SearchResult key={`${item.entity_type}-${item.entity_id}`} {...item} />)}
 * );
 * ```
 */
export function useGlobalSearch(
  options: UseGlobalSearchOptions = {}
): UseGlobalSearchReturn {
  const {
    entityTypes = null,
    startDate = null,
    endDate = null,
    limit = DEFAULT_LIMIT,
    enabled = true,
    tags = null,
  } = options;
  const {
    query,
    setQuery,
    debouncedQuery,
    isQueryValid,
    isDebouncing,
    clearSearch,
  } = useSearchCore();

  // Build the query - use the unified /search endpoint (same as search page)
  const queryResult = useQuery({
    queryKey: ['unifiedSearch', debouncedQuery, entityTypes, startDate, endDate, limit, tags],
    queryFn: () =>
      SearchService.unifiedSearchApiV1SearchGet({
        q: debouncedQuery,
        entityType: entityTypes,
        skip: 0,
        limit,
        startDate,
        endDate,
        tags,
      }),
    enabled: enabled && isQueryValid,
    staleTime: 30_000, // 30 seconds
    gcTime: 60_000, // 1 minute (renamed from cacheTime in v5)
    retry: 1,
  });

  const results = useMemo(() => {
    return queryResult.data?.results || [];
  }, [queryResult.data?.results]);

  const total = queryResult.data?.total || 0;
  const hasResults = isQueryValid && total > 0;

  return {
    query,
    setQuery,
    debouncedQuery,
    queryResult,
    isSearching: queryResult.isLoading || isDebouncing,
    hasResults,
    results,
    total,
    clearSearch,
  };
}

export default useGlobalSearch;
