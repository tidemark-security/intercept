import React from 'react';
import { Link } from '@/components/navigation/Link';
import { CaseAlertFilterCompact } from '@/components/entities/CaseAlertFilterCompact';
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
  filters,
  onFilterChange,
  statusOptions,
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
  emptyMessage = "No items found"
}: EntityListProps<T, F>) {
  const hasItems = items.length > 0;
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  return (
    <>
      {/* Filter Header */}
      <div className={`flex w-full flex-col items-start border-b border-solid  ${isDarkTheme ? 'border-brand-primary' : 'border-neutral-1000'} px-3 pt-3 pb-3 md:px-6 md:pt-6 md:pb-4`}>
        <div className="flex w-full flex-col items-start gap-4">
          <CaseAlertFilterCompact
            filters={filters as unknown as FilterState}
            onFilterChange={onFilterChange as unknown as (filters: FilterState) => void}
            assignees={users}
            assigneesLoading={usersLoading}
            statusOptions={statusOptions}
          />
        </div>
      </div>

      {/* Item List */}
      <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-3 p-6 mobile:p-2 overflow-auto">
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
              <div key={id} className="w-full">
                {content}
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
