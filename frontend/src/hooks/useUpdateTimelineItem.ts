import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import type { TimelineItem } from '@/types/timeline';
import { queryKeys } from './queryKeys';
import { findTimelineItem, updateTimelineItemById } from '@/utils/timelineUtils';
import { getTimelineItemMap } from '@/utils/timelineHelpers';

interface TimelineItemUpdate {
  itemId: string;
  updates: Partial<TimelineItem>; // Accept full timeline item data, not just flag/highlight
}

/**
 * Entity type for timeline operations
 */
export type EntityType = 'alert' | 'case' | 'task';

interface UseUpdateTimelineItemOptions {
  onSuccess?: (data: AlertRead | CaseRead | TaskRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to update a timeline item using TanStack Query mutation
 * Provides optimistic updates, automatic query invalidation, and error handling
 * 
 * @param entityId - The ID of the entity containing the timeline item
 * @param entityType - The type of entity ('alert' | 'case' | 'task')
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useUpdateTimelineItem(
  entityId: number | null | undefined,
  entityType: EntityType,
  options?: UseUpdateTimelineItemOptions
): UseMutationResult<AlertRead | CaseRead | TaskRead, Error, TimelineItemUpdate, { previousData: AlertRead | CaseRead | TaskRead | undefined }> {
  const queryClient = useQueryClient();

  return useMutation<AlertRead | CaseRead | TaskRead, Error, TimelineItemUpdate, { previousData: AlertRead | CaseRead | TaskRead | undefined }>({
    mutationFn: async ({ itemId, updates }: TimelineItemUpdate) => {
      if (!entityId) {
        throw new Error('Entity ID is required');
      }
      
      // Get the current data to find the full timeline item
      // Use partial key matching for all entity types to handle query keys with options like { includeLinkedTimelines }
      let queryKey: readonly (string | number)[];
      switch (entityType) {
        case 'alert':
          queryKey = queryKeys.alert.detailBase(entityId);
          break;
        case 'case':
          queryKey = queryKeys.case.detailBase(entityId);
          break;
        case 'task':
          queryKey = queryKeys.task.detailBase(entityId);
          break;
      }
      const queriesData = queryClient.getQueriesData<AlertRead | CaseRead | TaskRead>({ queryKey, exact: false });
      const currentData = queriesData.length > 0 ? queriesData[0][1] : undefined;
      const currentTimeline = getTimelineItemMap(currentData ?? null);
      
      // Find the item to update using shared utility
      const currentItem = currentTimeline ? findTimelineItem(currentTimeline, itemId) : null;
      if (!currentItem) {
        throw new Error('Timeline item not found');
      }
      
      // Merge the updates with the current item
      // Remove replies to avoid sending nested structures that would overwrite existing replies
      const { replies, ...itemWithoutReplies } = currentItem;
      const updatedItem = {
        ...itemWithoutReplies,
        ...updates,
        // Ensure id is preserved
        id: itemId,
      };
      
      // DO NOT include replies field at all - this prevents overwriting nested replies on the backend
      
      switch (entityType) {
        case 'alert':
          return AlertsService.updateTimelineItemApiV1AlertsAlertIdTimelineItemIdPut({
            alertId: entityId,
            itemId,
            requestBody: updatedItem,
          });
        case 'case':
          return CasesService.updateTimelineItemApiV1CasesCaseIdTimelineItemIdPut({
            caseId: entityId,
            itemId,
            requestBody: updatedItem,
          });
        case 'task':
          return TasksService.updateTimelineItemApiV1TasksTaskIdTimelineItemIdPut({
            taskId: entityId,
            itemId,
            requestBody: updatedItem,
          });
      }
    },
    
    // Optimistic update: immediately update the cache before the mutation completes
    onMutate: async ({ itemId, updates }: TimelineItemUpdate) => {
      if (!entityId) return { previousData: undefined };

      // Get the query key based on entity type
      let queryKey: readonly (string | number)[];
      switch (entityType) {
        case 'alert':
          queryKey = queryKeys.alert.detailBase(entityId);
          break;
        case 'case':
          queryKey = queryKeys.case.detailBase(entityId);
          break;
        case 'task':
          queryKey = queryKeys.task.detailBase(entityId);
          break;
      }

      // Cancel any outgoing refetches to prevent overwriting optimistic update
      await queryClient.cancelQueries({ queryKey, exact: false });

      // Snapshot the previous value for rollback
      const queriesData = queryClient.getQueriesData<AlertRead | CaseRead | TaskRead>({ queryKey, exact: false });
      const previousData = queriesData.length > 0 ? queriesData[0][1] : undefined;

      // Optimistically update the cache using shared utility
      const previousTimeline = getTimelineItemMap(previousData ?? null);
      if (previousData && previousTimeline) {
        const updatedData = {
          ...previousData,
          timeline_items: updateTimelineItemById(previousTimeline, itemId, updates) as any,
        };
        
        queryClient.setQueriesData<AlertRead | CaseRead | TaskRead>({ queryKey, exact: false }, updatedData);
      }

      // Return context with the previous value for rollback
      return { previousData };
    },

    // On error, roll back the optimistic update
    onError: (error, _variables, context) => {
      if (context?.previousData && entityId) {
        // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
        let queryKey: readonly (string | number)[];
        switch (entityType) {
          case 'alert':
            queryKey = queryKeys.alert.detailBase(entityId);
            break;
          case 'case':
            queryKey = queryKeys.case.detailBase(entityId);
            break;
          case 'task':
            queryKey = queryKeys.task.detailBase(entityId);
            break;
        }
        queryClient.setQueriesData({ queryKey, exact: false }, context.previousData);
      }
      console.error('Failed to update timeline item:', error);
      options?.onError?.(error);
    },

    // On success, update cache with server response (no need to refetch)
    onSuccess: (data) => {
      if (entityId) {
        // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
        let queryKey: readonly (string | number)[];
        switch (entityType) {
          case 'alert':
            queryKey = queryKeys.alert.detailBase(entityId);
            break;
          case 'case':
            queryKey = queryKeys.case.detailBase(entityId);
            break;
          case 'task':
            queryKey = queryKeys.task.detailBase(entityId);
            break;
        }
        queryClient.setQueriesData<AlertRead | CaseRead | TaskRead>({ queryKey, exact: false }, data);
      }

      options?.onSuccess?.(data);
    },
  });
}
