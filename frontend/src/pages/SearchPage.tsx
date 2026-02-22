/**
 * SearchPage - Dedicated full-page search with pagination
 * 
 * Features:
 * - Full-text search across Alerts, Cases, and Tasks
 * - Single entity type filtering with tabs
 * - Paginated results with navigation
 * - URL state for bookmarkable searches
 * - Date range filtering
 * 
 * @example
 * Navigated to from GlobalSearch "See all" or direct URL:
 * /search?q=phishing&type=alert&page=1
 */

import React, { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { Loader } from '@/components/feedback/Loader';
import { DateRangePicker, DateRangeValue } from '@/components/forms/DateRangePicker';
import { PaginationFooter } from '@/components/navigation/PaginationFooter';
import { useSearchPage } from '@/hooks/useSearchPage';
import type { SearchResultItem } from '@/types/generated/models/SearchResultItem';
import type { EntityType } from '@/types/generated/models/EntityType';
import { SearchFiltersBar, SearchPrompt, NoResults, SearchError } from '@/components/search';

import { SearchResultRow } from '@/components/search/SearchResultRow';
import { ExtendedSearchResultItem, getEntityPath, isSearchQueryValid } from '@/components/search/searchUtils';

import { AlertTriangle, NotebookPen, List, Search, X } from 'lucide-react';
/**
 * Get the icon component for an entity type
 */
function EntityIcon({ type }: { type: EntityType }) {
  switch (type) {
    case 'alert':
      return <AlertTriangle className="h-4 w-4 text-subtext-color" />;
    case 'case':
      return <NotebookPen className="h-4 w-4 text-subtext-color" />;
    case 'task':
      return <List className="h-4 w-4 text-subtext-color" />;
    default:
      return null;
  }
}

/**
 * Main SearchPage component
 */
export function SearchPage() {
  const navigate = useNavigate();

  const {
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
    isSearching,
    hasResults,
    clearSearch,
    dateRange,
    setDateRange,
    selectedTags,
    setSelectedTags,
  } = useSearchPage();

  // Convert dateRange to DateRangeValue format
  const dateRangeValue: DateRangeValue | null = dateRange.start || dateRange.end
    ? { start: dateRange.start || '', end: dateRange.end || '', preset: 'custom' }
    : null;

  const handleDateRangeChange = useCallback((value: DateRangeValue | null) => {
    setDateRange({
      start: value?.start || null,
      end: value?.end || null,
    });
  }, [setDateRange]);

  const navigateToResult = useCallback((item: SearchResultItem) => {
    const path = getEntityPath(item);
    navigate(path);
  }, [navigate]);

  const isQueryValid = isSearchQueryValid(debouncedQuery);

  const results = queryResult.data?.results || [];

  return (
    <DefaultPageLayout withContainer>
      <div className="container max-w-none flex h-full w-full flex-col items-start gap-6 py-8">
        {/* Header */}
        <div className="flex w-full items-center justify-between">
          <div className="flex flex-col gap-1">
            <span className="text-heading-1 font-heading-1 text-default-font">Search</span>
            <span className="text-body text-subtext-color">Search across alerts, cases, and tasks</span>
          </div>
        </div>
          
        {/* Search Input */}
        <div className="flex w-full items-center gap-3 bg-neutral-50 rounded-lg px-4 py-3">
          <Search className="text-xl text-subtext-color flex-shrink-0" />
          <input
            type="text"
            className="flex-1 h-auto bg-transparent border-none outline-none text-lg text-default-font placeholder:text-neutral-400"
            placeholder="Search alerts, cases, and tasks..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck="false"
          />
          {query && (
            <button
              type="button"
              onClick={clearSearch}
              className="p-1 rounded hover:bg-neutral-200 transition-colors"
              aria-label="Clear search"
            >
              <X className="h-5 w-5 text-neutral-400" />
            </button>
          )}
          {isSearching && (
            <Loader className="h-5 w-5" />
          )}
        </div>

        {/* Filters Row */}
        <SearchFiltersBar
          entityType={entityType}
          onEntityTypeChange={setEntityType}
          selectedTags={selectedTags}
          onTagsChange={setSelectedTags}
          dateRange={dateRangeValue}
          onDateRangeChange={handleDateRangeChange}
          datePickerVariant="neutral-secondary"
          className="px-0 pb-0 border-b-0"
        />

        {/* Results */}
        <div className="flex-1 w-full overflow-auto">
          {!isQueryValid ? (
            <SearchPrompt variant="page" />
          ) : queryResult.isError ? (
            <SearchError 
              error={queryResult.error} 
              onRetry={() => queryResult.refetch()}
              variant="page"
            />
          ) : isSearching && !queryResult.data ? (
            <div className="flex items-center justify-center py-16 w-full">
              <Loader className="h-8 w-8" />
            </div>
          ) : !hasResults ? (
            <NoResults query={debouncedQuery} variant="page" />
          ) : (
            <div className="flex flex-col gap-2">
              {results.map((item) => (
                <SearchResultRow
                  key={`${item.entity_type}-${item.entity_id}`}
                  item={item as ExtendedSearchResultItem}
                  onClick={() => navigateToResult(item)}
                  searchQuery={debouncedQuery}
                  icon={<EntityIcon type={item.entity_type} />}
                />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {hasResults && (
          <PaginationFooter
            currentPage={page + 1}
            totalPages={totalPages}
            totalResults={totalResults}
            onPageChange={(p) => setPage(p - 1)}
            className="mt-4"
          />
        )}
      </div>
    </DefaultPageLayout>
  );
}

export default SearchPage;
