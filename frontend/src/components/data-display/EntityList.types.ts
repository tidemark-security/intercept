import type { FilterState } from '@/types/filters';
import React from 'react';

/**
 * Props for the EntityList component
 */
export interface EntityListProps<T, F = FilterState> {
  /** Array of items to display */
  items: T[];
  
  /** Currently selected item ID (for highlighting) */
  selectedId: number | null;
  
  /** 
   * Callback when an item is selected (regular left-click)
   * @param id - Numeric item ID
   * @param humanId - Human-readable item ID (e.g., "A-001")
   */
  onSelect: (id: number, humanId: string) => void;
  
  /** Optional callback when an item is double-clicked */
  onDoubleClick?: (id: number, humanId: string) => void;
  
  /** 
   * Function to generate href for each item (enables middle-click/ctrl+click to open in new tab)
   * @param id - Numeric item ID
   * @param humanId - Human-readable item ID (e.g., "A-001")
   * @returns URL path for the item detail page
   */
  getItemHref?: (id: number, humanId: string) => string;
  
  /** Current filter state */
  filters: F;
  
  /** Callback when filters change */
  onFilterChange: (filters: F) => void;
  
  /** Options for the status filter dropdown */
  statusOptions?: { value: string; label: string }[];
  
  /** Current page number (1-indexed) */
  currentPage: number;
  
  /** Total number of pages */
  totalPages: number;
  
  /** Total number of items across all pages */
  totalItems?: number;
  
  /** Callback when page changes */
  onPageChange: (page: number) => void;

  /** Show paginator even when there is only one page */
  alwaysShowPaginator?: boolean;

  /** Optional content to render centered within paginator footer */
  paginatorCenterContent?: React.ReactNode;
  
  /** Loading state for items data */
  isLoading: boolean;
  
  /** Error state (null if no error) */
  error: Error | null;
  
  /** Available users for assignee filter */
  users: any[];
  
  /** Loading state for users data */
  usersLoading: boolean;
  
  /** Function to get IDs from item */
  getItemIds: (item: T) => { id: number; humanId: string };
  
  /** Function to map item to MenuCard props */
  mapItemToCard: (item: T) => {
    id: string;
    title: string;
    description: string;
    timestamp: React.ReactNode;
    assignee: string;
    tags: string | string[];
    // Uses MenuCard-compatible state (lowercase) - use taskStateToMenuCardState for task UIState
    state: 'new' | 'in_progress' | 'escalated' | 'closed' | 'closed_true_positive' | 'closed_benign_positive' | 'closed_false_positive' | 'closed_unresolved' | 'closed_duplicate' | 'tsk_todo' | 'tsk_in_progress' | 'tsk_done';
    // Uses UIPriority (lowercase) for priority - matches what priorityToUIPriority returns
    priority: 'info' | 'low' | 'medium' | 'high' | 'critical' | 'extreme';
  };
  
  /** Optional message to display when list is empty */
  emptyMessage?: string;
}
