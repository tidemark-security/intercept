import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import type { TimelineItem } from '@/types/timeline';
import { getQueueSearchQueryKey, type EntityType } from './queryKeys';
import { timelineItemCache, type TimelineMutationContext } from './timelineItemCache';

interface TimelineItemUpdate {
  itemId: string;
  updates: Partial<TimelineItem>; // Accept full timeline item data, not just flag/highlight
}

/**
 * Entity type for timeline operations
 */
export type { EntityType } from './queryKeys';

interface UseUpdateTimelineItemOptions {
  onSuccess?: (data: AlertRead | CaseRead | TaskRead) => void;
  onError?: (error: Error) => void;
}

function editableFields(item: Partial<TimelineItem>): Partial<TimelineItem> {
  const { created_at, replies, source_timeline_items, audit, ...fields } = item;
  return fields;
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
): UseMutationResult<AlertRead | CaseRead | TaskRead, Error, TimelineItemUpdate, TimelineMutationContext> {
  const queryClient = useQueryClient();
  const cache = timelineItemCache(queryClient, entityType, entityId);

  return useMutation<AlertRead | CaseRead | TaskRead, Error, TimelineItemUpdate, TimelineMutationContext>({
    mutationKey: cache.mutationKey,
    scope: cache.scope,
    mutationFn: async ({ itemId, updates }: TimelineItemUpdate) => {
      if (!entityId) {
        throw new Error('Entity ID is required');
      }
      
      const currentItem = cache.readItem(itemId);
      if (!currentItem) {
        throw new Error('Timeline item not found');
      }
      
      const updatedItem = { ...editableFields(currentItem), ...editableFields(updates), id: itemId };

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
    
    onMutate: ({ itemId, updates }) => cache.begin({
      type: 'update',
      itemId,
      updates: { ...editableFields(updates), id: itemId },
    }),

    onError: (error, _variables, context) => {
      cache.finish(context);
      console.error('Failed to update timeline item:', error);
      options?.onError?.(error);
    },

    onSuccess: (data, _variables, context) => {
      cache.finish(context, data);
      void queryClient.invalidateQueries({ queryKey: getQueueSearchQueryKey(entityType) });

      options?.onSuccess?.(data);
    },
  });
}
