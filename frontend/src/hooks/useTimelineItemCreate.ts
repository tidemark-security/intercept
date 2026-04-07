import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import { deleteDraft } from '@/utils/draftStorage';
import type { TimelineItemType } from '@/types/drafts';
import { getEntityQueryKey } from './queryKeys';

function normalizeTimelineItemMap(
  timelineItems: TimelineItemResponse['timeline_items']
): Record<string, any> {
  if (!timelineItems) {
    return {};
  }

  if (Array.isArray(timelineItems)) {
    return timelineItems.reduce<Record<string, any>>((accumulator, item) => {
      if (item && typeof item === 'object' && 'id' in item && typeof item.id === 'string') {
        accumulator[item.id] = item;
      }
      return accumulator;
    }, {});
  }

  return { ...timelineItems };
}

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
  /** Type-specific fields (observable_type, observable_value, etc.) */
  [key: string]: any;
}

/**
 * Context type for timeline items - 'alert', 'case', or 'task'
 */
export type TimelineContext = 'alert' | 'case' | 'task';

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
): UseMutationResult<{ response: TimelineItemResponse; itemId?: string }, Error, TimelineItemCreate, { previousData: TimelineItemResponse | undefined }> {
  const queryClient = useQueryClient();
  const context = options?.context || 'alert';

  return useMutation<
    { response: TimelineItemResponse; itemId?: string },
    Error,
    TimelineItemCreate,
    { previousData: TimelineItemResponse | undefined }
  >({
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

    // Optimistic update: Add temporary item to timeline if client ID provided
    onMutate: async (formData: TimelineItemCreate) => {
      if (entityId === null || !formData.id) {
        return { previousData: undefined };
      }

      // Determine the correct query key based on context
      const queryKey = getEntityQueryKey(context, entityId);

      // Cancel any outgoing refetches
      // Use partial key matching (exact: false) to handle query keys with options like includeLinkedTimelines
      await queryClient.cancelQueries({ queryKey, exact: false });

      // Snapshot the previous value
      // Use partial key matching to handle query keys with options
      const queriesData = queryClient.getQueriesData<TimelineItemResponse>({ queryKey, exact: false });
      const previousData: TimelineItemResponse | undefined =
        queriesData.length > 0 ? queriesData[0][1] : undefined;

      // Optimistically add the new item
      if (previousData) {
        const optimisticItem = {
          ...formData,
          id: formData.id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          // Mark as temporary for UI indication (optional)
          _optimistic: true,
        };

        const timelineItems = normalizeTimelineItemMap(previousData.timeline_items);

        const updatedData: TimelineItemResponse = {
          ...previousData,
          timeline_items: {
            ...timelineItems,
            [formData.id]: optimisticItem as any,
          } as any,
        };

        // Use partial key matching to handle query keys with options like includeLinkedTimelines
        queryClient.setQueriesData<TimelineItemResponse>({ queryKey, exact: false }, updatedData);
      }

      return { previousData };
    },

    // On error, roll back optimistic update and preserve draft
    onError: (error, formData, mutationContext) => {
      if (mutationContext?.previousData && entityId !== null) {
        const queryKey = getEntityQueryKey(context, entityId);
        // Use partial key matching to handle query keys with options like includeLinkedTimelines
        queryClient.setQueriesData({ queryKey, exact: false }, mutationContext.previousData);
      }
      
      console.error(`Failed to create ${context} timeline item:`, error);
      
      // TODO: Show error toast with validation messages
      // Example: showToast(error.message, 'error');
      
      // Draft is preserved automatically (not deleted on error)
      
      options?.onError?.(error);
    },

    // On success, update cache with server response and delete draft
    onSuccess: ({ response, itemId }, formData) => {
      // Update cache with server response
      if (entityId !== null) {
        const queryKey = getEntityQueryKey(context, entityId);
        // Use partial key matching to handle query keys with options like includeLinkedTimelines
        queryClient.setQueriesData<TimelineItemResponse>({ queryKey, exact: false }, response);
      }

      // Delete draft if enabled (default: true)
      if (options?.deleteDraftOnSuccess !== false && entityId !== null) {
        try {
          deleteDraft(entityId, formData.type as TimelineItemType);
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
