import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import type { TimelineItem } from '@/types/timeline';
import { queryKeys } from './queryKeys';
import { removeTimelineItemById } from '@/utils/timelineUtils';
import { getTimelineItemMap } from '@/utils/timelineHelpers';

interface DeleteTimelineItemParams {
  itemId: string;
}

/**
 * Entity type for timeline operations
 */
export type EntityType = 'alert' | 'case' | 'task';

interface UseDeleteTimelineItemOptions {
  onSuccess?: (data: AlertRead | CaseRead | TaskRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to delete a timeline item using TanStack Query mutation
 * Provides optimistic updates, automatic query invalidation, and error handling
 * 
 * @param entityId - The ID of the entity containing the timeline item
 * @param entityType - The type of entity ('alert' | 'case' | 'task')
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useDeleteTimelineItem(
  entityId: number | null,
  entityType: EntityType,
  options?: UseDeleteTimelineItemOptions
): UseMutationResult<AlertRead | CaseRead | TaskRead, Error, DeleteTimelineItemParams, { previousEntity: AlertRead | CaseRead | TaskRead | undefined }> {
  const queryClient = useQueryClient();

  return useMutation<AlertRead | CaseRead | TaskRead, Error, DeleteTimelineItemParams, { previousEntity: AlertRead | CaseRead | TaskRead | undefined }>({
    mutationFn: async ({ itemId }: DeleteTimelineItemParams) => {
      if (!entityId) {
        throw new Error('Entity ID is required');
      }
      switch (entityType) {
        case 'alert':
          return AlertsService.removeTimelineItemApiV1AlertsAlertIdTimelineItemIdDelete({
            alertId: entityId,
            itemId,
          });
        case 'case':
          return CasesService.removeTimelineItemApiV1CasesCaseIdTimelineItemIdDelete({
            caseId: entityId,
            itemId,
          });
        case 'task':
          return TasksService.removeTimelineItemApiV1TasksTaskIdTimelineItemIdDelete({
            taskId: entityId,
            itemId,
          });
      }
    },
    
    // Optimistic update: immediately remove the item from cache
    onMutate: async ({ itemId }: DeleteTimelineItemParams) => {
      if (!entityId) return { previousEntity: undefined };

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
      const previousEntity = queriesData.length > 0 ? queriesData[0][1] : undefined;

      // Optimistically update the cache by removing the item using shared utility
      const previousTimeline = getTimelineItemMap(previousEntity ?? null);
      if (previousEntity && previousTimeline) {
        const updatedEntity = {
          ...previousEntity,
          timeline_items: removeTimelineItemById(previousTimeline, itemId) as any,
        };
        
        queryClient.setQueriesData<AlertRead | CaseRead | TaskRead>({ queryKey, exact: false }, updatedEntity);
      }

      // Return context with the previous value for rollback
      return { previousEntity };
    },

    // On error, roll back the optimistic update
    onError: (error, _variables, context) => {
      if (context?.previousEntity && entityId) {
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
        queryClient.setQueriesData({ queryKey, exact: false }, context.previousEntity);
      }
      console.error('Failed to delete timeline item:', error);
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
