import { useQuery } from '@tanstack/react-query';
import type { Page_TaskRead_ } from '@/types/generated/models/Page_TaskRead_';
import type { TaskStatus } from '@/types/generated/models/TaskStatus';
import { TasksService } from '@/types/generated/services/TasksService';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS, QUERY_REFETCH_INTERVALS_WS } from '@/config/queryConfig';
import { useWebSocket } from '@/contexts/WebSocketContext';

export interface UseTasksParams {
  page?: number;
  size?: number;
  status?: TaskStatus[] | null;
  assignee?: string | null;
  caseId?: number | null;
  search?: string | null;
  startDate?: string | null;
  endDate?: string | null;
}

/**
 * TanStack Query hook for fetching paginated tasks list with filtering
 * 
 * @example
 * ```tsx
 * const { data, isLoading, error } = useTasks({
 *   page: 1,
 *   size: 50,
 *   status: ['TODO', 'IN_PROGRESS'],
 *   assignee: 'john.doe',
 *   search: 'urgent'
 * });
 * ```
 */
export function useTasks({
  page = 1,
  size = 50,
  status = null,
  assignee = null,
  caseId = null,
  search = null,
  startDate = null,
  endDate = null,
}: UseTasksParams = {}) {
  const { isConnected } = useWebSocket();

  return useQuery<Page_TaskRead_, Error>({
    queryKey: ['tasks', { page, size, status, assignee, caseId, search, startDate, endDate }],
    queryFn: async () => {
      const response = await TasksService.getTasksApiV1TasksGet({
        page,
        size,
        status: status || undefined,
        assignee: assignee || undefined,
        caseId: caseId || undefined,
        search: search || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      });

      return response as Page_TaskRead_;
    },
    staleTime: QUERY_STALE_TIMES.LIST, // 1 minute
    refetchInterval: isConnected ? QUERY_REFETCH_INTERVALS_WS.LIST : QUERY_REFETCH_INTERVALS.LIST,
    refetchIntervalInBackground: false, // Pause polling when tab is inactive
  });
}
