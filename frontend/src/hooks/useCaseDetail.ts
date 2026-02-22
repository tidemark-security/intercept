import { useQuery } from '@tanstack/react-query';
import type { CaseReadWithAlerts } from '@/types/generated/models/CaseReadWithAlerts';
import { CasesService } from '@/types/generated/services/CasesService';
import { queryKeys } from './queryKeys';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS } from '@/config/queryConfig';

/**
 * Options for useCaseDetail hook
 */
export interface UseCaseDetailOptions {
  /**
   * When true, alert and task timeline items will include source_timeline_items
   * containing the timeline from the linked entity
   */
  includeLinkedTimelines?: boolean;
}

/**
 * TanStack Query hook for fetching a single case with full details including alerts and timeline
 * 
 * @param caseId - The numeric ID of the case to fetch (null to skip fetching)
 * @param options - Optional configuration including includeLinkedTimelines
 * 
 * @example
 * ```tsx
 * // Basic usage
 * const { data: caseDetail, isLoading, error } = useCaseDetail(selectedCaseId);
 * 
 * // With linked timelines (embeds alert/task timelines in their timeline items)
 * const { data: caseDetail } = useCaseDetail(selectedCaseId, { includeLinkedTimelines: true });
 * ```
 */
export function useCaseDetail(
  caseId: number | null,
  options: UseCaseDetailOptions = {}
) {
  const { includeLinkedTimelines = false } = options;

  return useQuery<CaseReadWithAlerts | null, Error>({
    queryKey: queryKeys.case.detail(caseId, { includeLinkedTimelines }),
    queryFn: async () => {
      if (caseId === null) {
        return null;
      }

      const response = await CasesService.getCaseApiV1CasesCaseIdGet({
        caseId,
        includeLinkedTimelines,
      });

      return response;
    },
    enabled: caseId !== null, // Only fetch when we have a case ID
    staleTime: QUERY_STALE_TIMES.REALTIME, // 30 seconds for real-time collaboration
    refetchInterval: QUERY_REFETCH_INTERVALS.DETAIL, // 30 seconds
    refetchIntervalInBackground: false, // Pause polling when tab is inactive
    // Don't retry on 404 errors to show NotFoundError immediately
    retry: (failureCount, error) => {
      if ((error as any)?.status === 404 || (error as any)?.response?.status === 404) {
        return false;
      }
      return failureCount < 3;
    },
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
  });
}
