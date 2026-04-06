import { useQuery } from '@tanstack/react-query';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import { TasksService } from '@/types/generated/services/TasksService';
import { queryKeys } from './queryKeys';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS, QUERY_REFETCH_INTERVALS_WS } from '@/config/queryConfig';
import { convertTaskHumanIdToNumeric } from '@/utils/humanIdHelpers';
import { useRealtimeSubscription } from './useRealtimeSubscription';
import { hasActiveTimelineEnrichments } from '@/utils/enrichmentState';

/**
 * Options for useTaskDetail hook
 */
export interface UseTaskDetailOptions {
  /**
   * When true, case and alert timeline items will include source_timeline_items
   * containing the timeline from the linked entity
   */
  includeLinkedTimelines?: boolean;
}

/**
 * TanStack Query hook for fetching a single task by ID
 * 
 * @param taskId - The task ID (numeric or human ID like TSK-0000001)
 * @param options - Optional configuration including includeLinkedTimelines
 * @returns Query result with task data
 * 
 * @example
 * ```tsx
 * const { data: task, isLoading, error } = useTaskDetail(123);
 * // or with linked timelines
 * const { data: task } = useTaskDetail(123, { includeLinkedTimelines: true });
 * ```
 */
export function useTaskDetail(
  taskId: number | string | null,
  options: UseTaskDetailOptions = {}
) {
  const { includeLinkedTimelines = false } = options;
  const numericId = typeof taskId === 'number'
    ? taskId
    : taskId !== null
      ? (convertTaskHumanIdToNumeric(taskId) ?? null)
      : null;
  const { isConnected } = useRealtimeSubscription('task', numericId);

  return useQuery<TaskRead, Error>({
    queryKey: queryKeys.task.detail(taskId, { includeLinkedTimelines }),
    queryFn: async () => {
      if (!taskId) {
        throw new Error('Task ID is required');
      }

      const numericTaskId =
        typeof taskId === 'number'
          ? taskId
          : convertTaskHumanIdToNumeric(taskId) ?? Number(taskId);

      if (!Number.isFinite(numericTaskId) || Number.isNaN(numericTaskId)) {
        throw new Error('Task ID must be numeric or a valid human ID');
      }

      return await TasksService.getTaskApiV1TasksTaskIdGet({ 
        taskId: numericTaskId,
        includeLinkedTimelines,
      });
    },
    enabled: taskId !== null,
    staleTime: QUERY_STALE_TIMES.REALTIME, // 30 seconds for real-time collaboration
    refetchInterval: (query) => {
      if (hasActiveTimelineEnrichments(query.state.data)) {
        return QUERY_REFETCH_INTERVALS.ENRICHMENT_ACTIVE;
      }
      return isConnected ? QUERY_REFETCH_INTERVALS_WS.DETAIL : QUERY_REFETCH_INTERVALS.DETAIL;
    },
    refetchIntervalInBackground: false, // Pause polling when tab is inactive
    // Don't retry on 404 errors to show NotFoundError immediately
    retry: (failureCount, error) => {
      if ((error as any)?.status === 404 || (error as any)?.response?.status === 404) {
        return false;
      }
      return failureCount < 3;
    },
  });
}
