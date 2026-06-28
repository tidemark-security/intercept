import { useQuery } from '@tanstack/react-query';
import type { Page_CaseRead_ } from '@/types/generated/models/Page_CaseRead_';
import type { CaseStatus } from '@/types/generated/models/CaseStatus';
import { CasesService } from '@/types/generated/services/CasesService';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS, QUERY_REFETCH_INTERVALS_WS } from '@/config/queryConfig';
import { useWebSocket } from '@/contexts/WebSocketContext';

export interface UseCasesParams {
  page?: number;
  size?: number;
  status?: CaseStatus[] | null;
  assignee?: string | null;
  includeTags?: string[] | null;
  excludeTags?: string[] | null;
  search?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  sortBy?: string;
  sortOrder?: string;
}

/**
 * TanStack Query hook for fetching paginated cases list with filtering
 * 
 * @example
 * ```tsx
 * const { data, isLoading, error } = useCases({
 *   page: 1,
 *   size: 50,
 *   status: ['NEW', 'IN_PROGRESS'],
 *   assignee: 'john.doe',
 *   search: 'phishing'
 * });
 * ```
 */
export function useCases({
  page = 1,
  size = 50,
  status = null,
  assignee = null,
  includeTags = null,
  excludeTags = null,
  search = null,
  startDate = null,
  endDate = null,
  sortBy = 'created_at',
  sortOrder = 'desc',
}: UseCasesParams = {}) {
  const { isConnected } = useWebSocket();

  return useQuery<Page_CaseRead_, Error>({
    queryKey: ['cases', { page, size, status, assignee, includeTags, excludeTags, search, startDate, endDate, sortBy, sortOrder }],
    queryFn: async () => {
      const response = await CasesService.getCasesApiV1CasesGet({
        page,
        size,
        status: status || undefined,
        assignee: assignee || undefined,
        includeTags: includeTags || undefined,
        excludeTags: excludeTags || undefined,
        search: search || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        sortBy,
        sortOrder,
      });

      return response as Page_CaseRead_;
    },
    staleTime: QUERY_STALE_TIMES.LIST, // 1 minute
    refetchInterval: isConnected ? QUERY_REFETCH_INTERVALS_WS.LIST : QUERY_REFETCH_INTERVALS.LIST,
    refetchIntervalInBackground: false, // Pause polling when tab is inactive
  });
}
