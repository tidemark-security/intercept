
"use client";
/*
 * Paginator Component
 * A reusable pagination component with smart page number display logic
 * 
 * Features:
 * - Consistent number of page slots on mobile (5) and desktop (7)
 * - Fixed-width buttons for both numbers and ellipsis
 * - Smart ellipsis display (only when needed, never for small page counts)
 * - Responsive design with reduced buttons on mobile
 */

import React from "react";

import { cn } from "@/utils/cn";
import { Button } from "@/components/buttons/Button";
import { IconButton } from "@/components/buttons/IconButton";

import { ChevronFirst, ChevronLast, ChevronLeft, ChevronRight } from 'lucide-react';
interface PaginatorProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Current page number (1-indexed) */
  currentPage: number;
  /** Total number of pages */
  totalPages: number;
  /** Callback when page changes */
  onPageChange: (page: number) => void;
  /** Whether pagination controls should be disabled */
  disabled?: boolean;
  className?: string;
}

/**
 * Generate smart page number array with ellipsis
 * 
 * Logic:
 * - Always show first and last page when possible
 * - Show pages around current page
 * - Use ellipsis only when there's a gap of more than 1 page
 * - Each ellipsis counts as 1 slot
 * - Strictly limit total slots to maxSlots
 */
function generatePageNumbers(currentPage: number, totalPages: number, maxSlots: number): (number | 'ellipsis-start' | 'ellipsis-end')[] {
  // If we can show all pages, do it
  if (totalPages <= maxSlots) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const pages: (number | 'ellipsis-start' | 'ellipsis-end')[] = [];
  
  // We need at least 3 slots: first, ellipsis/middle, last
  if (maxSlots < 3) {
    // Fallback for very small maxSlots
    return [currentPage];
  }
  
  // Determine if we're near the start or end
  const nearStart = currentPage <= 3;
  const nearEnd = currentPage >= totalPages - 2;
  
  if (nearStart) {
    // Near start: [1] [2] [3] [4] [...] [last]
    // Fill from start, leave room for ellipsis and last page
    const endPage = Math.min(totalPages - 1, maxSlots - 2);
    for (let i = 1; i <= endPage; i++) {
      pages.push(i);
    }
    if (endPage < totalPages - 1) {
      pages.push('ellipsis-end');
    }
    if (totalPages > 1) {
      pages.push(totalPages);
    }
  } else if (nearEnd) {
    // Near end: [1] [...] [n-3] [n-2] [n-1] [n]
    // Show first, ellipsis, then fill from end
    pages.push(1);
    const startPage = Math.max(2, totalPages - maxSlots + 3);
    if (startPage > 2) {
      pages.push('ellipsis-start');
    }
    for (let i = startPage; i <= totalPages; i++) {
      pages.push(i);
    }
  } else {
    // In the middle: [1] [...] [current-1] [current] [current+1] [...] [last]
    // We have: first (1) + ellipsis (1) + middle pages (?) + ellipsis (1) + last (1) = maxSlots
    // So middle pages = maxSlots - 4
    const middleSlots = maxSlots - 4;
    const sidePages = Math.floor(middleSlots / 2);
    
    pages.push(1);
    pages.push('ellipsis-start');
    
    // Show pages around current
    const rangeStart = currentPage - sidePages;
    const rangeEnd = currentPage + sidePages;
    
    for (let i = rangeStart; i <= rangeEnd; i++) {
      if (i > 1 && i < totalPages) {
        pages.push(i);
      }
    }
    
    pages.push('ellipsis-end');
    pages.push(totalPages);
  }
  
  return pages;
}

export const Paginator = React.forwardRef<HTMLDivElement, PaginatorProps>(
  function Paginator(
    { currentPage, totalPages, onPageChange, disabled = false, className, ...otherProps },
    ref
  ) {
    // Detect mobile breakpoint
    const [isMobile, setIsMobile] = React.useState(false);
    
    React.useEffect(() => {
      const checkMobile = () => {
        setIsMobile(window.innerWidth < 768); // md breakpoint
      };
      
      checkMobile();
      window.addEventListener('resize', checkMobile);
      return () => window.removeEventListener('resize', checkMobile);
    }, []);

    const maxSlots = isMobile ? 5 : 7;
    const isFirstPage = currentPage === 1;
    const isLastPage = currentPage >= totalPages;
    const hasPages = totalPages > 0;

    const pageNumbers = React.useMemo(
      () => generatePageNumbers(currentPage, totalPages, maxSlots),
      [currentPage, totalPages, maxSlots]
    );

    return (
      <div
        ref={ref}
        className={cn(
          "flex w-full items-center justify-center gap-2 md:gap-6 rounded-md",
          className
        )}
        {...otherProps}
      >
        {/* First and Previous buttons */}
        <div className="flex items-center justify-center">
          <IconButton
            icon={<ChevronFirst />}
            onClick={() => onPageChange(1)}
            disabled={isFirstPage || !hasPages || disabled}
          />
          <IconButton
            icon={<ChevronLeft />}
            onClick={() => onPageChange(currentPage - 1)}
            disabled={isFirstPage || !hasPages || disabled}
          />
        </div>

        {/* Page numbers */}
        <div className="flex items-center justify-center gap-1">
          {hasPages && totalPages > 0 ? (
            pageNumbers.map((pageNum, idx) => {
              if (pageNum === 'ellipsis-start' || pageNum === 'ellipsis-end') {
                return (
                  <Button
                    key={pageNum}
                    variant="neutral-tertiary"
                    disabled
                    className="w-10 px-0"
                  >
                    ...
                  </Button>
                );
              }
              return (
                <Button
                  key={pageNum}
                  variant={currentPage === pageNum ? "neutral-secondary" : "neutral-tertiary"}
                  onClick={() => onPageChange(pageNum)}
                  disabled={disabled}
                  className="w-10 px-0"
                >
                  {pageNum}
                </Button>
              );
            })
          ) : (
            <Button variant="neutral-secondary" disabled className="w-10 px-0">
              1
            </Button>
          )}
        </div>

        {/* Next and Last buttons */}
        <div className="flex items-center justify-center">
          <IconButton
            icon={<ChevronRight />}
            onClick={() => onPageChange(currentPage + 1)}
            disabled={isLastPage || !hasPages || disabled}
          />
          <IconButton
            icon={<ChevronLast />}
            onClick={() => onPageChange(totalPages)}
            disabled={isLastPage || !hasPages || disabled}
          />
        </div>
      </div>
    );
  }
);
