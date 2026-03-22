import React from 'react';
import { Button } from '@/components/buttons/Button';


import { ChevronLeft, ChevronRight } from 'lucide-react';
export interface PaginationFooterProps {
  /** Current page number (1-indexed) */
  currentPage: number;
  /** Total number of pages */
  totalPages: number;
  /** Total number of results */
  totalResults?: number;
  /** Callback when page changes (1-indexed) */
  onPageChange: (page: number) => void;
  /** Optional centered content between result count and page controls */
  centerContent?: React.ReactNode;
  /** Show footer even when there is only one page */
  alwaysShow?: boolean;
  /** Optional className for the container */
  className?: string;
}

/**
 * Generate smart page number array with ellipsis
 */
function generatePageNumbers(
  currentPage: number,
  totalPages: number
): (number | 'ellipsis-start' | 'ellipsis-end')[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages: (number | 'ellipsis-start' | 'ellipsis-end')[] = [];
  const showEllipsisStart = currentPage > 3;
  const showEllipsisEnd = currentPage < totalPages - 2;

  // Always show first page
  pages.push(1);

  if (showEllipsisStart) {
    pages.push('ellipsis-start');
  }

  // Show pages around current
  for (let i = Math.max(2, currentPage - 1); i <= Math.min(totalPages - 1, currentPage + 1); i++) {
    if (!pages.includes(i)) {
      pages.push(i);
    }
  }

  if (showEllipsisEnd) {
    pages.push('ellipsis-end');
  }

  // Always show last page
  if (totalPages > 1 && !pages.includes(totalPages)) {
    pages.push(totalPages);
  }

  return pages;
}

/**
 * PaginationFooter - Reusable pagination component with results count
 * 
 * Displays total results on the left and pagination controls on the right.
 * Uses 1-indexed page numbers for consistency with UI display.
 */
export function PaginationFooter({
  currentPage,
  totalPages,
  totalResults,
  onPageChange,
  centerContent,
  alwaysShow = false,
  className = '',
}: PaginationFooterProps) {
  if (!alwaysShow && totalPages <= 1) return null;

  const pageNumbers = generatePageNumbers(currentPage, totalPages);
  const isFirstPage = currentPage === 1;
  const isLastPage = currentPage >= totalPages;

  return (
    <div
      className={`w-full border-t border-neutral-border px-4 py-4 ${className}`}
    >
      <div className="flex flex-col items-center gap-3 md:grid md:grid-cols-[1fr_auto_1fr] md:items-center md:gap-4">
        <span className="text-sm text-subtext-color md:justify-self-start">
          {totalResults !== undefined
            ? `${totalResults.toLocaleString()} result${totalResults !== 1 ? 's' : ''}`
            : ''}
        </span>

        {centerContent ? (
          <div className="md:justify-self-center">{centerContent}</div>
        ) : (
          <div className="hidden md:block" />
        )}

        <div className="flex items-center gap-1 md:justify-self-end">
          <Button
            variant="neutral-tertiary"
            size="small"
            icon={<ChevronLeft />}
            onClick={() => onPageChange(currentPage - 1)}
            disabled={isFirstPage}
          />
          {pageNumbers.map((p, i) =>
            p === 'ellipsis-start' || p === 'ellipsis-end' ? (
              <span key={`${p}-${i}`} className="px-2 text-subtext-color">…</span>
            ) : (
              <Button
                key={p}
                variant={p === currentPage ? 'brand-primary' : 'neutral-tertiary'}
                size="small"
                onClick={() => onPageChange(p)}
                className="min-w-[32px]"
              >
                {p}
              </Button>
            )
          )}
          <Button
            variant="neutral-tertiary"
            size="small"
            icon={<ChevronRight />}
            onClick={() => onPageChange(currentPage + 1)}
            disabled={isLastPage}
          />
        </div>
      </div>
    </div>
  );
}
