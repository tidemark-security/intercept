import React from 'react';
import { Link } from '@/components/navigation/Link';
import { EntityFilterToolbar } from '@/components/entities/EntityFilterToolbar';
import { MenuCard } from '@/components/cards/MenuCard';
import { PaginationFooter } from '@/components/navigation/PaginationFooter';
import type { EntityListProps } from './EntityList.types';
import type { FilterState } from '@/types/filters';
import { useTheme } from '@/contexts/ThemeContext';

/**
 * EntityList - Generic component for displaying paginated list of entities with filtering
 */
export function EntityList<T, F = FilterState>({
  items,
  selectedId,
  onSelect,
  onDoubleClick,
  getItemHref,
  selectable = false,
  selectedIds,
  onSelectionChange,
  onSelectVisible,
  toolbarActions,
  filters,
  onFilterChange,
  statusOptions,
  enableTagFilters = false,
  currentPage,
  totalPages,
  totalItems,
  onPageChange,
  alwaysShowPaginator = false,
  paginatorCenterContent,
  isLoading,
  error,
  users,
  usersLoading,
  mapItemToCard,
  getItemIds,
  onTagClick,
  emptyMessage = "No items found"
}: EntityListProps<T, F>) {
  const hasItems = items.length > 0;
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const visibleIds = items.map((item) => getItemIds(item).id);
  const visibleTagCounts = React.useMemo(() => {
    const counts = new Map<string, number>();

    items.forEach((item) => {
      const tags = mapItemToCard(item).tags;
      const tagList = Array.isArray(tags)
        ? tags
        : tags
          ? tags.split(',').map((tag) => tag.trim())
          : [];

      tagList
        .filter(Boolean)
        .forEach((tag) => counts.set(tag, (counts.get(tag) ?? 0) + 1));
    });

    return Array.from(counts.entries())
      .map(([tag, count]) => ({ tag, count }))
      .sort((left, right) => right.count - left.count || left.tag.localeCompare(right.tag));
  }, [items, mapItemToCard]);
  const selectedVisibleCount = visibleIds.filter((id) => selectedIds?.has(id)).length;
  const allVisibleSelected = visibleIds.length > 0 && selectedVisibleCount === visibleIds.length;
  const someVisibleSelected = selectedVisibleCount > 0 && !allVisibleSelected;

  return (
    <>
      {/* Filter Header */}
      <div className={`flex w-full flex-col items-start border-b border-solid  ${isDarkTheme ? 'border-brand-primary' : 'border-neutral-1000'} px-3 pt-3 pb-3 md:px-6 md:pt-6 md:pb-4`}>
        <div className="flex w-full flex-col items-start gap-4">
          <EntityFilterToolbar
            filters={filters as unknown as FilterState}
            onFilterChange={onFilterChange as unknown as (filters: FilterState) => void}
            assignees={users}
            assigneesLoading={usersLoading}
            statusOptions={statusOptions}
            showTagFilters={enableTagFilters}
            availableTags={visibleTagCounts}
            actions={toolbarActions}
          />
        </div>
      </div>

      {/* Item List */}
      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-3 p-6 mobile:p-2 overflow-auto">
        {selectable && hasItems && (
          <div className="flex w-full items-center gap-3 border-b border-solid border-neutral-border pb-3">
            <input
              type="checkbox"
              aria-label="Select visible alerts"
              checked={allVisibleSelected}
              ref={(input) => {
                if (input) input.indeterminate = someVisibleSelected;
              }}
              onChange={(event) => onSelectVisible?.(event.target.checked, visibleIds)}
              className="h-4 w-4 shrink-0"
            />
            <span className="text-caption font-caption text-subtext-color">
              {selectedIds?.size ? `${selectedIds.size} selected` : 'Select visible alerts'}
            </span>
          </div>
        )}
        {isLoading ? (
          <div className="flex w-full items-center justify-center py-8">
            <span className="text-body font-body text-subtext-color">Loading...</span>
          </div>
        ) : error ? (
          <div className="flex w-full items-center justify-center py-8">
            <span className="text-body font-body text-error-color">Error loading items</span>
          </div>
        ) : items.length > 0 ? (
          items.map((item) => {
            const cardProps = mapItemToCard(item);
            const { id, humanId } = getItemIds(item);
            const href = getItemHref?.(id, humanId);
            const isRowSelected = selectedIds?.has(id) ?? false;
            
            /**
             * Handle click events on the menu card.
             * - Regular left-click: prevent default, call onSelect (allows preview mode)
             * - Middle-click / Ctrl+click / Cmd+click: let browser handle natively (opens in new tab)
             */
            const handleClick = (e: React.MouseEvent) => {
              // Let browser handle middle-click or modifier-key clicks natively
              if (e.button === 1 || e.ctrlKey || e.metaKey || e.shiftKey) {
                return; // Don't prevent default - let the <Link> handle it
              }
              // Regular left-click: use custom handler
              e.preventDefault();
              onSelect(id, humanId);
            };
            
            const menuCard = (
              <MenuCard
                {...cardProps}
                variant={selectedId === id ? 'selected' : undefined}
                onClick={handleClick}
                onTagClick={onTagClick}
              />
            );
            
            // Wrap in Link if href is provided (enables native new-tab behavior)
            const content = href ? (
              <Link 
                to={href} 
                className="block w-full no-underline"
                onDoubleClick={onDoubleClick ? (e) => {
                  e.preventDefault();
                  onDoubleClick(id, humanId);
                } : undefined}
              >
                {menuCard}
              </Link>
            ) : (
              <div
                onDoubleClick={onDoubleClick ? () => {
                  onDoubleClick(id, humanId);
                } : undefined}
                className="w-full"
              >
                {menuCard}
              </div>
            );
            
            return (
              <div key={id} className="flex w-full items-start gap-3">
                {selectable && (
                  <input
                    type="checkbox"
                    aria-label={`Select ${humanId}`}
                    checked={isRowSelected}
                    onChange={(event) => onSelectionChange?.(id, event.target.checked)}
                    onClick={(event) => event.stopPropagation()}
                    className="mt-4 h-4 w-4 shrink-0"
                  />
                )}
                <div className="min-w-0 flex-1">
                {content}
                </div>
              </div>
            );
          })
        ) : (
          <div className="flex w-full items-center justify-center py-8">
            <span className="text-body font-body text-subtext-color">{emptyMessage}</span>
          </div>
        )}
      </div>

      {/* Pagination Footer */}
      <PaginationFooter
        currentPage={currentPage}
        totalPages={totalPages}
        totalResults={totalItems}
        onPageChange={onPageChange}
        alwaysShow={alwaysShowPaginator}
        centerContent={paginatorCenterContent}
      />
    </>
  );
}
