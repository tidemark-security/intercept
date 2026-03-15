import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { Page_AlertRead_ } from '@/types/generated/models/Page_AlertRead_';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { Priority } from '@/types/generated/models/Priority';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS, QUERY_REFETCH_INTERVALS_WS } from '@/config/queryConfig';
import { useWebSocket } from '@/contexts/WebSocketContext';

interface UseAlertsOptions {
  status?: AlertStatus[] | null;
  assignee?: string[] | null;
  caseId?: number | null;
  priority?: Priority[] | null;
  source?: string | null;
  hasCase?: boolean | null;
  startDate?: string | null;
  endDate?: string | null;
  search?: string | null;
  sortBy?: string;
  sortOrder?: string;
  page?: number;
  size?: number;
}

/**
 * Hook to fetch alerts from the API using TanStack Query
 * Provides caching, automatic refetching, and loading/error states
 */
export function useAlerts(
  options: UseAlertsOptions = {}
): UseQueryResult<Page_AlertRead_, Error> {
  const {
    status = null,
    assignee = null,
    caseId = null,
    priority = null,
    source = null,
    hasCase = null,
    startDate = null,
    endDate = null,
    search = null,
    sortBy = 'created_at',
    sortOrder = 'desc',
    page = 1,
    size = 50,
  } = options;

  const { isConnected } = useWebSocket();

  return useQuery({
    queryKey: ['alerts', { status, assignee, caseId, priority, source, hasCase, startDate, endDate, search, sortBy, sortOrder, page, size }],
    queryFn: () =>
      AlertsService.getAlertsApiV1AlertsGet({
        status,
        assignee,
        caseId,
        priority,
        source,
        hasCase,
        startDate,
        endDate,
        search,
        sortBy,
        sortOrder,
        page,
        size,
      }),
    staleTime: QUERY_STALE_TIMES.LIST, // 1 minute
    refetchInterval: isConnected ? QUERY_REFETCH_INTERVALS_WS.LIST : QUERY_REFETCH_INTERVALS.LIST,
    refetchIntervalInBackground: false, // Pause polling when tab is inactive
  });
}
