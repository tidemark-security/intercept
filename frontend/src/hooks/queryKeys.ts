/**
 * Centralized Query Key Factory
 * 
 * This module provides a single source of truth for all TanStack Query keys,
 * ensuring consistency across the application and preventing cache invalidation bugs.
 * 
 * Usage:
 * - Use `queryKeys.entity.detail(id, options)` for detail queries
 * - Use `queryKeys.entity.list(filters)` for list queries
 * - Use `getEntityQueryKey(entityType, id)` for dynamic entity type resolution
 * 
 * @see TIMELINE-IMPROVEMENTS.md for more context
 */

import type { FilterState, CaseFilterState, TaskFilterState } from '@/types/filters';

/**
 * Options for detail queries that support linked timeline expansion
 */
export interface DetailQueryOptions {
  /** When true, linked entity timelines are embedded in timeline items */
  includeLinkedTimelines?: boolean;
}

/**
 * Entity types supported by the query key factory
 */
export type EntityType = 'alert' | 'case' | 'task';

/**
 * Centralized query key factory for all entity types.
 * 
 * Ensures consistent key structure across:
 * - Detail hooks (useAlertDetail, useCaseDetail, useTaskDetail)
 * - Mutation hooks (useTimelineItemCreate, useUpdateTimelineItem, etc.)
 * - Update hooks (useUpdateAlert, useUpdateCase, useUpdateTask)
 * 
 * @example
 * ```typescript
 * // In a detail hook
 * queryKey: queryKeys.alert.detail(alertId, { includeLinkedTimelines })
 * 
 * // In a mutation hook for cache operations
 * queryClient.cancelQueries({ queryKey: queryKeys.alert.detail(entityId), exact: false })
 * ```
 */
export const queryKeys = {
  alert: {
    /**
     * Query key for a single alert detail
     * @param id - Alert ID
     * @param options - Optional configuration including includeLinkedTimelines
     */
    detail: (id: number | null, options?: DetailQueryOptions) =>
      ['alert-detail', id, options ?? {}] as const,
    
    /**
     * Base query key for partial matching (excludes options)
     * Use with `exact: false` for cache operations that need to match all variants
     * @param id - Alert ID
     */
    detailBase: (id: number) => ['alert-detail', id] as const,
    
    /**
     * Query key for alert list with optional filters
     * @param filters - Optional filter state
     */
    list: (filters?: FilterState) => ['alerts', filters] as const,
    
    /**
     * Base query key for all alerts lists
     */
    listBase: () => ['alerts'] as const,
  },
  
  case: {
    /**
     * Query key for a single case detail
     * @param id - Case ID
     * @param options - Optional configuration including includeLinkedTimelines
     */
    detail: (id: number | null, options?: DetailQueryOptions) =>
      ['case', id, options ?? {}] as const,
    
    /**
     * Base query key for partial matching (excludes options)
     * Use with `exact: false` for cache operations that need to match all variants
     * @param id - Case ID
     */
    detailBase: (id: number) => ['case', id] as const,
    
    /**
     * Query key for case list with optional filters
     * @param filters - Optional filter state
     */
    list: (filters?: CaseFilterState) => ['cases', filters] as const,
    
    /**
     * Base query key for all cases lists
     */
    listBase: () => ['cases'] as const,
  },
  
  task: {
    /**
     * Query key for a single task detail
     * @param id - Task ID (numeric or string human ID like TSK-0000001)
     * @param options - Optional configuration including includeLinkedTimelines
     */
    detail: (id: number | string | null, options?: DetailQueryOptions) =>
      ['task', id, options ?? {}] as const,
    
    /**
     * Base query key for partial matching (excludes options)
     * Use with `exact: false` for cache operations that need to match all variants
     * @param id - Task ID
     */
    detailBase: (id: number | string) => ['task', id] as const,
    
    /**
     * Query key for task list with optional filters
     * @param filters - Optional filter state
     */
    list: (filters?: TaskFilterState) => ['tasks', filters] as const,
    
    /**
     * Base query key for all tasks lists
     */
    listBase: () => ['tasks'] as const,
  },
} as const;

/**
 * Helper to get the base query key for an entity type.
 * Useful for partial matching in cache operations.
 * 
 * @param entityType - The type of entity ('alert' | 'case' | 'task')
 * @param entityId - The ID of the entity
 * @returns Base query key tuple for use with `exact: false`
 * 
 * @example
 * ```typescript
 * // Cancel all queries for this alert (regardless of options)
 * await queryClient.cancelQueries({ 
 *   queryKey: getEntityQueryKey('alert', alertId), 
 *   exact: false 
 * });
 * ```
 */
export function getEntityQueryKey(
  entityType: EntityType,
  entityId: number | string
): readonly [string, number | string] {
  switch (entityType) {
    case 'alert':
      return queryKeys.alert.detailBase(entityId as number);
    case 'case':
      return queryKeys.case.detailBase(entityId as number);
    case 'task':
      return queryKeys.task.detailBase(entityId);
  }
}

/**
 * Helper to get the list query key for an entity type.
 * Useful for invalidating list queries after mutations.
 * 
 * @param entityType - The type of entity ('alert' | 'case' | 'task')
 * @returns Base list query key tuple
 * 
 * @example
 * ```typescript
 * // Invalidate all list queries for alerts
 * queryClient.invalidateQueries({ queryKey: getEntityListQueryKey('alert') });
 * ```
 */
export function getEntityListQueryKey(
  entityType: EntityType
): readonly [string] {
  switch (entityType) {
    case 'alert':
      return queryKeys.alert.listBase();
    case 'case':
      return queryKeys.case.listBase();
    case 'task':
      return queryKeys.task.listBase();
  }
}
