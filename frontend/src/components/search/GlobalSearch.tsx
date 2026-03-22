/**
 * GlobalSearch - Command palette for unified search across Alerts, Cases, and Tasks
 * 
 * Features:
 * - Opens with Cmd+K (macOS) or Ctrl+K (Windows/Linux)
 * - Debounced full-text search with fuzzy fallback
 * - Ranked results (flat list, sorted by relevance score)
 * - Keyboard navigation support
 * - Click to navigate to entity detail page
 * 
 * @example
 * ```tsx
 * <GlobalSearch open={isSearchOpen} onOpenChange={setIsSearchOpen} />
 * ```
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Dialog } from '@/components/overlays/Dialog';
import { Loader } from '@/components/feedback/Loader';
import { Badge } from '@/components/data-display/Badge';
import { type DateRangeValue } from '@/components/forms/DateRangePicker';
import { useGlobalSearch } from '@/hooks/useGlobalSearch';
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';
import type { SearchResultItem } from '@/types/generated/models/SearchResultItem';
import type { EntityType } from '@/types/generated/models/EntityType';

import { SearchResultRow } from '@/components/search/SearchResultRow';
import { ExtendedSearchResultItem, getEntityPath, isSearchQueryValid } from '@/components/search/searchUtils';
import {
  SearchFiltersBar,
  SearchPrompt,
  NoResults,
  SearchError,
  loadDateRangePreference,
  loadSelectedEntityTypePreference,
  saveDateRangePreference,
  saveSelectedEntityTypePreference,
} from '@/components/search';

import { ArrowRight, Search, X } from 'lucide-react';
interface GlobalSearchProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GlobalSearch({ open, onOpenChange }: GlobalSearchProps) {
  const navigate = useNavigate();
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRowRefs = useRef<Array<HTMLDivElement | null>>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  
  // Entity type filter with sessionStorage persistence (single selection: 'all' | EntityType)
  const [selectedEntityType, setSelectedEntityType] = useState<EntityType | 'all'>(loadSelectedEntityTypePreference);
  
  // Date range filter with sessionStorage persistence
  const [dateRange, setDateRange] = useState<DateRangeValue | null>(loadDateRangePreference);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  
  // Convert selected type to array of enabled entity types for API
  const enabledEntityTypes = React.useMemo(() => {
    if (selectedEntityType === 'all') return null; // null = all types (API default)
    return [selectedEntityType as EntityType];
  }, [selectedEntityType]);
  
  // Handle ToggleGroup value change (single selection)
  const handleToggleGroupChange = useCallback((value: EntityType | 'all') => {
    if (!value) return; // Don't allow deselecting
    setSelectedEntityType(value);
    saveSelectedEntityTypePreference(value);
  }, []);

  // Handle date range change
  const handleDateRangeChange = useCallback((value: DateRangeValue | null) => {
    setDateRange(value);
    saveDateRangePreference(value);
  }, []);

  const {
    query,
    setQuery,
    debouncedQuery,
    queryResult,
    isSearching,
    hasResults,
    results,
    total,
    clearSearch,
  } = useGlobalSearch({ 
    enabled: open,
    entityTypes: enabledEntityTypes,
    startDate: dateRange?.start || null,
    endDate: dateRange?.end || null,
    tags: selectedTags.length > 0 ? selectedTags : null,
    limit: 10,
  });

  const isQueryValidShared = isSearchQueryValid(debouncedQuery);

  // Results are already a flat list sorted by score (from the API)
  const allResults = useMemo(() => results ?? [], [results]);

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [allResults.length]);

  // Keep row refs aligned with current results length
  useEffect(() => {
    resultRowRefs.current = resultRowRefs.current.slice(0, allResults.length);
  }, [allResults.length]);

  // Ensure keyboard-selected row stays visible in scrollable results viewport
  useEffect(() => {
    if (!open || allResults.length === 0) return;

    const selectedRow = resultRowRefs.current[selectedIndex];
    if (!selectedRow) return;

    selectedRow.scrollIntoView({ block: 'nearest' });
  }, [open, selectedIndex, allResults.length]);

  // Focus input when opening
  useEffect(() => {
    if (open) {
      // Slight delay to ensure dialog is mounted
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    } else {
      // Clear search when closing
      clearSearch();
      setSelectedIndex(0);
    }
  }, [open, clearSearch]);

  const handleClose = useCallback(() => {
    onOpenChange(false);
  }, [onOpenChange]);

  // Navigate to search page with current query (for "View more results" link)
  const handleViewMore = useCallback(() => {
    const params = new URLSearchParams();
    params.set('q', debouncedQuery);
    if (selectedEntityType !== 'all') {
      params.set('type', selectedEntityType);
    }
    if (dateRange?.start) {
      params.set('start', dateRange.start);
    }
    if (dateRange?.end) {
      params.set('end', dateRange.end);
    }
    selectedTags.forEach((tag) => params.append('tag', tag));
    handleClose();
    navigate(`/search?${params.toString()}`);
  }, [navigate, handleClose, debouncedQuery, selectedEntityType, dateRange, selectedTags]);

  const navigateToResult = useCallback((item: SearchResultItem) => {
    const path = getEntityPath(item);
    handleClose();
    navigate(path);
  }, [navigate, handleClose]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, allResults.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (allResults[selectedIndex]) {
          navigateToResult(allResults[selectedIndex]);
        }
        break;
      case 'Escape':
        e.preventDefault();
        handleClose();
        break;
    }
  }, [allResults, selectedIndex, navigateToResult, handleClose]);

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className="w-[min(80rem,calc(100vw-2rem))] h-[min(56rem,calc(100vh-2rem))] max-h-[calc(100vh-2rem)] p-0 overflow-hidden shadow-none ">
        {/* Search Input */}
        <div className="flex w-full items-center gap-3 border-b border-solid border-neutral-border px-6 py-4">
          <Search className="text-[24px] text-subtext-color flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            className="flex-1 h-auto bg-transparent border-none outline-none text-2xl text-default-font placeholder:text-neutral-400"
            placeholder="Search alerts, cases, and tasks..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Search"
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck="false"
          />
          {query && (
            <button
              type="button"
              onClick={clearSearch}
              className="p-1 rounded hover:bg-neutral-100 transition-colors"
              aria-label="Clear search"
            >
              <X className="h-5 w-5 text-neutral-400" />
            </button>
          )}
          {isSearching && (
            <Loader className="h-5 w-5" />
          )}
        </div>

        {/* Entity Type Filters */}
        <SearchFiltersBar
          entityType={selectedEntityType}
          onEntityTypeChange={handleToggleGroupChange}
          selectedTags={selectedTags}
          onTagsChange={setSelectedTags}
          dateRange={dateRange}
          onDateRangeChange={handleDateRangeChange}
          datePickerVariant="neutral-tertiary"
        />

        {/* Results */}
        <div className="flex min-h-0 grow w-full flex-col items-start gap-2 py-4 overflow-auto" role="listbox">
          {!isQueryValidShared ? (
            <SearchPrompt variant="modal" />
          ) : queryResult.isError ? (
            <SearchError 
              error={queryResult.error} 
              onRetry={() => queryResult.refetch()}
              variant="modal"
            />
          ) : isSearching ? (
            <div className="flex items-center justify-center py-8 w-full">
              <Loader className="h-6 w-6" />
            </div>
          ) : !hasResults ? (
            <NoResults query={debouncedQuery} variant="modal" />
          ) : (
            <>
              {/* Flat list of results ranked by score */}
              <div className="flex w-full flex-col items-start">
                {allResults.map((item, i) => (
                  <div
                    key={`${item.entity_type}-${item.entity_id}`}
                    ref={(element) => {
                      resultRowRefs.current[i] = element;
                    }}
                    className="w-full"
                  >
                    <SearchResultRow
                      item={item as ExtendedSearchResultItem}
                      isSelected={selectedIndex === i}
                      onClick={() => navigateToResult(item)}
                      onMouseEnter={() => setSelectedIndex(i)}
                      searchQuery={debouncedQuery}
                      role="option"
                    />
                  </div>
                ))}
              </div>
              {/* View more results link */}
              {total > allResults.length && (
                <button
                  type="button"
                  onClick={handleViewMore}
                  className="group flex w-full items-center justify-center gap-2 px-4 py-3 hover:bg-neutral-50 transition-colors border-t border-solid border-neutral-border"
                >
                  <span
                    className={cn('text-caption font-caption', {
                      'text-brand-primary group-hover:text-brand-400': isDarkTheme,
                      'text-brand-700 group-hover:text-brand-800': !isDarkTheme,
                    })}
                  >
                    View all {total} results
                  </span>
                  <ArrowRight
                    className={cn('text-body font-body h-4 w-4', {
                      'text-brand-primary group-hover:text-brand-400': isDarkTheme,
                      'text-brand-700 group-hover:text-brand-800': !isDarkTheme,
                    })}
                  />
                </button>
              )}
            </>
          )}
        </div>

        {/* Footer with keyboard hints */}
        <div className="flex w-full items-center justify-between border-t border-solid border-neutral-border px-6 py-3">
          <div className="flex w-48 flex-none items-center gap-4">
            <div className="flex items-center gap-2">
              <Badge variant="neutral">↑↓</Badge>
              <span className="text-caption font-caption text-subtext-color">
                Navigate
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="neutral">↵</Badge>
              <span className="text-caption font-caption text-subtext-color">
                Open
              </span>
            </div>
          </div>
          <span className="grow shrink-0 basis-0 text-caption font-caption text-subtext-color text-center">
            {hasResults ? `${total} results` : ''}
          </span>
          <div className="flex w-48 flex-none items-center justify-end gap-2">
            <Badge variant="neutral">ESC</Badge>
            <span className="text-caption font-caption text-subtext-color">
              Close
            </span>
          </div>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}

export default GlobalSearch;
