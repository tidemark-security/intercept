import { useSearchParams } from 'react-router-dom';
import { useCallback, useMemo } from 'react';
import type { FilterState, CaseFilterState, TaskFilterState } from '@/types/filters';
import { formatForBackend, parseRelativeTime } from '@/utils/dateFilters';

// Union of all filter state types
type AnyFilterState = FilterState | CaseFilterState | TaskFilterState;

/**
 * Parse URL search params into a filter state object.
 * Supports: search, status (comma-separated), assignee (comma-separated), alert tag filters, dateRange (start/end)
 */
export function parseFiltersFromURL(searchParams: URLSearchParams): Partial<AnyFilterState> {
  const filters: Partial<AnyFilterState> = {};
  const alertFilters = filters as Partial<FilterState>;

  const search = searchParams.get('search');
  if (search) filters.search = search;

  const status = searchParams.get('status');
  if (status) {
    filters.status = status.split(',').filter(Boolean) as any[];
  }

  const assignee = searchParams.get('assignee');
  if (assignee) {
    filters.assignee = assignee.split(',').filter(Boolean);
  }

  const includeTags = parseListParam(searchParams, 'include_tags');
  if (includeTags.length > 0) {
    alertFilters.includeTags = includeTags;
  }

  const excludeTags = parseListParam(searchParams, 'exclude_tags');
  if (excludeTags.length > 0) {
    alertFilters.excludeTags = excludeTags;
  }

  const timeframe = searchParams.get('timeframe');
  const relativeRange = timeframe ? parseRelativeTime(timeframe) : null;
  if (timeframe && relativeRange) {
    filters.dateRange = {
      start: formatForBackend(relativeRange.start),
      end: formatForBackend(relativeRange.end),
      preset: timeframe,
    };
  } else {
    const startDate = searchParams.get('start_date');
    const endDate = searchParams.get('end_date');
    if (startDate || endDate) {
      filters.dateRange = {
        start: startDate || '',
        end: endDate || '',
        preset: 'custom',
      };
    }
  }

  return filters;
}

function parseListParam(searchParams: URLSearchParams, key: string): string[] {
  const values = searchParams
    .getAll(key)
    .flatMap((value) => value.split(','))
    .map((value) => value.trim())
    .filter(Boolean);

  return Array.from(new Set(values));
}

/**
 * Convert filter state to URL search params.
 */
export function filtersToURLParams(filters: AnyFilterState, page?: number): URLSearchParams {
  const params = new URLSearchParams();

  if (filters.search) {
    params.set('search', filters.search);
  }

  if (filters.status && filters.status.length > 0) {
    params.set('status', filters.status.join(','));
  }

  if (filters.assignee && filters.assignee.length > 0) {
    params.set('assignee', filters.assignee.join(','));
  }

  const alertFilters = filters as Partial<FilterState>;
  alertFilters.includeTags?.forEach((tag) => {
    const cleanTag = tag.trim();
    if (cleanTag) params.append('include_tags', cleanTag);
  });
  alertFilters.excludeTags?.forEach((tag) => {
    const cleanTag = tag.trim();
    if (cleanTag) params.append('exclude_tags', cleanTag);
  });

  if (filters.dateRange?.preset && filters.dateRange.preset !== 'custom') {
    params.set('timeframe', filters.dateRange.preset);
  } else if (filters.dateRange) {
    if (filters.dateRange.start) {
      params.set('start_date', filters.dateRange.start);
    }
    if (filters.dateRange.end) {
      params.set('end_date', filters.dateRange.end);
    }
  }

  // Only add page to URL if it's greater than 1 (page 1 is the default)
  if (page && page > 1) {
    params.set('page', String(page));
  }

  return params;
}

interface UseURLFiltersOptions<T extends AnyFilterState> {
  /** Default filter values when no URL params present */
  defaults: T;
}

interface UseURLFiltersResult<T extends AnyFilterState> {
  /** Current filter state (derived from URL) */
  filters: T;
  /** Update filters (resets page to 1) */
  setFilters: (filters: T) => void;
  /** Current page number (1-indexed) */
  currentPage: number;
  /** Update current page */
  setCurrentPage: (page: number) => void;
}

/**
 * Hook to sync filter state and pagination with URL query parameters.
 * 
 * - On mount: parses URL params and merges with defaults
 * - On filter change: updates URL params and resets page to 1
 * - On page change: updates URL params
 * - Supports back/forward navigation
 * 
 * @param options Configuration options
 * @returns Object with filters, setFilters, currentPage, setCurrentPage
 */
export function useURLFilters<T extends AnyFilterState>(
  options: UseURLFiltersOptions<T>
): UseURLFiltersResult<T> {
  const { defaults } = options;
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Parse current URL params into filter state
  const urlFilters = useMemo(() => parseFiltersFromURL(searchParams), [searchParams]);
  
  // Parse page from URL (default to 1)
  const pageParam = searchParams.get('page');
  const currentPage = pageParam ? Math.max(1, parseInt(pageParam, 10) || 1) : 1;
  
  // Merge URL filters with defaults (URL takes precedence for specified values)
  // Use useMemo to maintain stable reference when values haven't changed
  const filters = useMemo<T>(() => {
    const parsedAlertFilters = urlFilters as Partial<FilterState>;
    const defaultAlertFilters = defaults as Partial<FilterState>;

    return {
      ...defaults,
      ...urlFilters,
      // Handle status specially - only override if URL has status param
      status: urlFilters.status !== undefined ? urlFilters.status : defaults.status,
      // Handle assignee specially - only override if URL has assignee param
      assignee: urlFilters.assignee !== undefined ? urlFilters.assignee : defaults.assignee,
      // Handle alert tag filters specially - only override if URL has tag params
      includeTags: parsedAlertFilters.includeTags !== undefined ? parsedAlertFilters.includeTags : defaultAlertFilters.includeTags,
      excludeTags: parsedAlertFilters.excludeTags !== undefined ? parsedAlertFilters.excludeTags : defaultAlertFilters.excludeTags,
    } as T;
  }, [defaults, urlFilters]);

  // Update URL when filters change (resets page to 1)
  const setFilters = useCallback((newFilters: T) => {
    const params = filtersToURLParams(newFilters, 1); // Reset to page 1
    setSearchParams(params, { replace: true });
  }, [setSearchParams]);

  // Update URL when page changes - preserves current URL params, only updates page
  const setCurrentPage = useCallback((page: number) => {
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      if (page > 1) {
        params.set('page', String(page));
      } else {
        params.delete('page');
      }
      return params;
    }, { replace: true });
  }, [setSearchParams]);

  return { filters, setFilters, currentPage, setCurrentPage };
}
