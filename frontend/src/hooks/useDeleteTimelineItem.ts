import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import { getQueueSearchQueryKey, type EntityType } from './queryKeys';
import { timelineItemCache, type TimelineMutationContext } from './timelineItemCache';

interface DeleteTimelineItemParams {
  itemId: string;
}

/**
 * Entity type for timeline operations
 */
export type { EntityType } from './queryKeys';

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
): UseMutationResult<AlertRead | CaseRead | TaskRead, Error, DeleteTimelineItemParams, TimelineMutationContext> {
  const queryClient = useQueryClient();
  const cache = timelineItemCache(queryClient, entityType, entityId);

  return useMutation<AlertRead | CaseRead | TaskRead, Error, DeleteTimelineItemParams, TimelineMutationContext>({
    mutationKey: cache.mutationKey,
    scope: cache.scope,
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
    
    onMutate: ({ itemId }) => cache.begin({ type: 'delete', itemId }),

    onError: (error, _variables, context) => {
      cache.finish(context);
      console.error('Failed to delete timeline item:', error);
      options?.onError?.(error);
    },

    onSuccess: (data, _variables, context) => {
      cache.finish(context, data);
      void queryClient.invalidateQueries({ queryKey: getQueueSearchQueryKey(entityType) });

      options?.onSuccess?.(data);
    },
  });
}
