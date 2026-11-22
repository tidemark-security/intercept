import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import { deleteDraft } from '@/utils/draftStorage';
import type { TimelineItemType } from '@/types/drafts';
import { createOptimisticTimelineItem } from '@/utils/timelineUtils';
import { getQueueSearchQueryKey, type EntityType } from './queryKeys';
import { timelineItemCache, type TimelineMutationContext } from './timelineItemCache';

/**
 * Timeline item creation payload
 * This matches the structure expected by the backend API
 */
export interface TimelineItemCreate {
  /** Client-generated UUID for optimistic updates */
  id?: string;
  /** Timeline item type (note, observable, system, etc.) */
  type: string;
  /** Item description/content */
  description?: string;
  /** Timestamp when the event was observed */
  timestamp?: string;
  /** Tags for categorization */
  tags?: string[];
  /** Flag status */
  flagged?: boolean;
  /** Highlight status */
  highlighted?: boolean;
  /** The item to attach a reply to */
  parent_id?: string | null;
  /** Type-specific fields (observable_type, observable_value, etc.) */
  [key: string]: any;
}

/**
 * Context type for timeline items - 'alert', 'case', or 'task'
 */
export type TimelineContext = EntityType;

/**
 * Response type for timeline item creation (union of AlertRead, CaseRead, and TaskRead)
 */
export type TimelineItemResponse = AlertRead | CaseRead | TaskRead;

interface UseTimelineItemCreateOptions {
  /** Callback when item is successfully created */
  onSuccess?: (data: TimelineItemResponse, itemId?: string) => void;
  /** Callback when creation fails */
  onError?: (error: Error) => void;
  /** Whether to delete draft on success (default: true) */
  deleteDraftOnSuccess?: boolean;
  /** Context type: 'alert' or 'case' (default: 'alert') */
  context?: TimelineContext;
  /** Optional parent item ID for creating replies - will be injected into all mutations */
  parentItemId?: string | null;
}

/**
 * Hook for creating timeline items with TanStack Query mutation
 * 
 * Supports both alert and case timelines with the same interface.
 * 
 * Features:
 * - Works with both alerts and cases
 * - Automatic cache invalidation/update
 * - Draft deletion on success
 * - Metrics emission
 * - Error handling
 * - Optimistic updates (when client ID provided)
 * 
 * @param entityId - The ID of the alert or case to add the timeline item to
 * @param options - Optional callbacks and configuration
 * @returns Mutation object with mutate, isPending, isError, error properties
 * 
 * @example Alert timeline
 * ```tsx
 * const createItem = useTimelineItemCreate(alertId, {
 *   context: 'alert', // default
 *   onSuccess: (data, itemId) => {
 *     console.log('Item created:', itemId);
 *     onClose();
 *   },
 *   onError: (error) => {
 *     showToast('Failed to create item', 'error');
 *   }
 * });
 * ```
 * 
 * @example Case timeline
 * ```tsx
 * const createItem = useTimelineItemCreate(caseId, {
 *   context: 'case',
 *   onSuccess: (data, itemId) => {
 *     console.log('Item created:', itemId);
 *   }
 * });
 * ```
 */
export function useTimelineItemCreate(
  entityId: number | null,
  options?: UseTimelineItemCreateOptions
): UseMutationResult<{ response: TimelineItemResponse; itemId?: string }, Error, TimelineItemCreate, TimelineMutationContext> {
  const queryClient = useQueryClient();
  const context = options?.context || 'alert';
  const cache = timelineItemCache(queryClient, context, entityId);

  return useMutation<
    { response: TimelineItemResponse; itemId?: string },
    Error,
    TimelineItemCreate,
    TimelineMutationContext
  >({
    mutationKey: cache.mutationKey,
    scope: cache.scope,
    mutationFn: async (formData: TimelineItemCreate) => {
      if (entityId === null) {
        throw new Error(`${context === 'alert' ? 'Alert' : context === 'case' ? 'Case' : 'Task'} ID is required`);
      }

      // Inject parent_id if provided via options
      const dataWithParent = options?.parentItemId
        ? { ...formData, parent_id: options.parentItemId }
        : formData;

      // Call the appropriate service based on context
      let response: TimelineItemResponse;
      if (context === 'alert') {
        response = await AlertsService.addTimelineItemApiV1AlertsAlertIdTimelinePost({
          alertId: entityId,
          requestBody: dataWithParent,
        });
      } else if (context === 'case') {
        response = await CasesService.addTimelineItemApiV1CasesCaseIdTimelinePost({
          caseId: entityId,
          requestBody: dataWithParent,
        });
      } else {
        response = await TasksService.addTimelineItemApiV1TasksTaskIdTimelinePost({
          taskId: entityId,
          requestBody: dataWithParent,
        });
      }

      return { response, itemId: formData.id };
    },

    onMutate: (formData) => {
      const parentId = options?.parentItemId || formData.parent_id || null;
      const optimisticItem = formData.id
        ? { ...createOptimisticTimelineItem({ ...formData, parent_id: parentId }), _optimistic: true }
        : undefined;
      return cache.begin({ type: 'create', parentId, item: optimisticItem });
    },

    onError: (error, _formData, mutationContext) => {
      cache.finish(mutationContext);
      
      console.error(`Failed to create ${context} timeline item:`, error);
      
      // TODO: Show error toast with validation messages
      // Example: showToast(error.message, 'error');
      
      // Draft is preserved automatically (not deleted on error)
      
      options?.onError?.(error);
    },

    onSuccess: ({ response, itemId }, formData, mutationContext) => {
      cache.finish(mutationContext, response);
      void queryClient.invalidateQueries({ queryKey: getQueueSearchQueryKey(context) });

      // Delete draft if enabled (default: true)
      if (options?.deleteDraftOnSuccess !== false && entityId !== null) {
        try {
          deleteDraft(entityId, formData.type as TimelineItemType, context);
        } catch (error) {
          console.warn('Failed to delete draft after successful creation:', error);
        }
      }

      // Emit metric
      try {
        // TODO: Implement metrics utility
        // emitMetric('timeline_item_created', {
        //   context: context,
        //   item_type: formData.type,
        //   source: 'right_dock', // or 'quick_terminal'
        //   has_tags: formData.tags && formData.tags.length > 0,
        // });
        console.debug('Metric: timeline_item_created', {
          context: context,
          item_type: formData.type,
          item_id: itemId,
        });
      } catch (error) {
        console.warn('Failed to emit metric:', error);
      }

      options?.onSuccess?.(response, itemId);
    },
  });
}
