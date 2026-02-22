import { useQuery } from '@tanstack/react-query';
import type { Page_CaseRead_ } from '@/types/generated/models/Page_CaseRead_';
import type { CaseStatus } from '@/types/generated/models/CaseStatus';
import { CasesService } from '@/types/generated/services/CasesService';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS } from '@/config/queryConfig';

export interface UseCasesParams {
  page?: number;
  size?: number;
  status?: CaseStatus[] | null;
  assignee?: string | null;
  search?: string | null;
  startDate?: string | null;
  endDate?: string | null;
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
  search = null,
  startDate = null,
  endDate = null,
}: UseCasesParams = {}) {
  return useQuery<Page_CaseRead_, Error>({
    queryKey: ['cases', { page, size, status, assignee, search, startDate, endDate }],
    queryFn: async () => {
      const response = await CasesService.getCasesApiV1CasesGet({
        page,
        size,
        status: status || undefined,
        assignee: assignee || undefined,
        search: search || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      });

      return response as Page_CaseRead_;
    },
    staleTime: QUERY_STALE_TIMES.LIST, // 1 minute
    refetchInterval: QUERY_REFETCH_INTERVALS.LIST, // 60 seconds
    refetchIntervalInBackground: false, // Pause polling when tab is inactive
  });
}
