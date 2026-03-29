import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { EnrichmentsService } from '@/types/generated/services/EnrichmentsService';
import { getEntityQueryKey, type EntityType } from './queryKeys';

const ENRICHMENT_ENQUEUE_DELAY_MS = 500;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

interface UseEnqueueItemEnrichmentOptions {
  onSuccess?: (taskId: string | null) => void;
  onError?: (error: Error) => void;
}

interface EnqueueItemEnrichmentVariables {
  itemId: string;
}

interface EnqueueItemEnrichmentResponse {
  enqueued?: boolean;
  task_id?: string | null;
}

interface TimelineItemLike {
  id?: string | null;
  replies?: TimelineItemLike[] | null;
  enrichment_status?: string | null;
  enrichment_task_id?: string | null;
}

interface EntityDetailWithTimeline {
  timeline_items?: TimelineItemLike[] | null;
}

interface EnqueueItemEnrichmentContext {
  previousDetailQueries: Array<[readonly unknown[], unknown]>;
  itemId: string;
}

function updateTimelineItems(
  items: TimelineItemLike[] | null | undefined,
  itemId: string,
  updateItem: (item: TimelineItemLike) => TimelineItemLike,
): { items: TimelineItemLike[] | null | undefined; changed: boolean } {
  if (!Array.isArray(items) || items.length === 0) {
    return { items, changed: false };
  }

  let changed = false;
  const nextItems = items.map((item) => {
    let nextItem = item;

    if (item.id === itemId) {
      nextItem = updateItem(item);
      changed = changed || nextItem !== item;
    }

    if (Array.isArray(item.replies) && item.replies.length > 0) {
      const updatedReplies = updateTimelineItems(item.replies, itemId, updateItem);
      if (updatedReplies.changed) {
        nextItem = {
          ...nextItem,
          replies: updatedReplies.items ?? null,
        };
        changed = true;
      }
    }

    return nextItem;
  });

  return changed ? { items: nextItems, changed: true } : { items, changed: false };
}

function updateCachedEntityTimeline<T>(
  data: T,
  itemId: string,
  updateItem: (item: TimelineItemLike) => TimelineItemLike,
): T {
  if (!data || typeof data !== 'object' || !("timeline_items" in (data as object))) {
    return data;
  }

  const entity = data as T & EntityDetailWithTimeline;
  const updated = updateTimelineItems(entity.timeline_items, itemId, updateItem);
  if (!updated.changed) {
    return data;
  }

  return {
    ...entity,
    timeline_items: updated.items ?? null,
  };
}

function markItemEnrichmentPending(item: TimelineItemLike): TimelineItemLike {
  if (item.enrichment_status === 'pending') {
    return item;
  }

  return {
    ...item,
    enrichment_status: 'pending',
  };
}

function setItemEnrichmentTaskId(item: TimelineItemLike, taskId: string | null): TimelineItemLike {
  if (!taskId || item.enrichment_task_id === taskId) {
    return item;
  }

  return {
    ...item,
    enrichment_task_id: taskId,
  };
}

function restorePreviousDetailQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  previousDetailQueries: Array<[readonly unknown[], unknown]>,
): void {
  for (const [queryKey, queryData] of previousDetailQueries) {
    queryClient.setQueryData(queryKey, queryData);
  }
}

export function useEnqueueItemEnrichment(
  entityType: EntityType,
  entityId: number | null,
  options?: UseEnqueueItemEnrichmentOptions,
): UseMutationResult<EnqueueItemEnrichmentResponse, Error, EnqueueItemEnrichmentVariables> {
  const queryClient = useQueryClient();
  const detailQueryKey = entityId !== null ? getEntityQueryKey(entityType, entityId) : null;

  return useMutation<EnqueueItemEnrichmentResponse, Error, EnqueueItemEnrichmentVariables, EnqueueItemEnrichmentContext>({
    mutationFn: async ({ itemId }) => {
      if (entityId === null) {
        throw new Error('Entity ID is required');
      }

      await delay(ENRICHMENT_ENQUEUE_DELAY_MS);

      return EnrichmentsService.enqueueItemEnrichmentApiV1EnrichmentsEntityTypeEntityIdItemsItemIdEnqueuePost({
        entityType,
        entityId,
        itemId,
      });
    },
    onMutate: ({ itemId }) => {
      if (detailQueryKey === null) {
        return { previousDetailQueries: [], itemId };
      }

      void queryClient.cancelQueries({
        queryKey: detailQueryKey,
        exact: false,
      });

      const previousDetailQueries = queryClient.getQueriesData({
        queryKey: detailQueryKey,
        exact: false,
      });

      queryClient.setQueriesData(
        { queryKey: detailQueryKey, exact: false },
        (currentData: unknown) => updateCachedEntityTimeline(currentData, itemId, markItemEnrichmentPending),
      );

      return { previousDetailQueries, itemId };
    },
    onSuccess: (data, _variables, context) => {
      if (detailQueryKey !== null) {
        const taskId = data.task_id ?? null;
        if (taskId && context?.itemId) {
          queryClient.setQueriesData(
            { queryKey: detailQueryKey, exact: false },
            (currentData: unknown) =>
              updateCachedEntityTimeline(currentData, context.itemId, (item) => setItemEnrichmentTaskId(item, taskId)),
          );
        }
      }

      options?.onSuccess?.(data.task_id ?? null);
    },
    onError: (error, _variables, context) => {
      restorePreviousDetailQueries(queryClient, context?.previousDetailQueries ?? []);
      options?.onError?.(error);
    },
  });
}