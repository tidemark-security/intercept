import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AlertReadWithCase } from '@/types/generated/models/AlertReadWithCase';
import { queryKeys } from './queryKeys';
import { QUERY_STALE_TIMES, QUERY_REFETCH_INTERVALS, QUERY_REFETCH_INTERVALS_WS } from '@/config/queryConfig';
import { useRealtimeSubscription } from './useRealtimeSubscription';
import { hasActiveTimelineEnrichments } from '@/utils/enrichmentState';

/**
 * Options for useAlertDetail hook
 */
export interface UseAlertDetailOptions {
  /**
   * When true, case and task timeline items will include source_timeline_items
   * containing the timeline from the linked entity
   */
  includeLinkedTimelines?: boolean;
}

/**
 * Hook to fetch a single alert's detailed information from the API using TanStack Query
 * Provides caching, automatic refetching, and loading/error states
 * Automatically cancels previous requests when alertId changes
 * 
 * @param alertId - The ID of the alert to fetch (or null to skip fetching)
 * @param options - Optional configuration including includeLinkedTimelines
 * @returns Query result with alert detail data, loading state, and error state
 */
export function useAlertDetail(
  alertId: number | null,
  options: UseAlertDetailOptions = {}
): UseQueryResult<AlertReadWithCase, Error> {
  const { includeLinkedTimelines = false } = options;
  const { isConnected } = useRealtimeSubscription('alert', alertId);

  return useQuery({
    queryKey: queryKeys.alert.detail(alertId, { includeLinkedTimelines }),
    queryFn: () => {
      if (!alertId) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.getAlertApiV1AlertsAlertIdGet({
        alertId,
        includeLinkedTimelines,
      });
    },
    enabled: alertId !== null, // Only fetch when alertId is provided
    staleTime: QUERY_STALE_TIMES.REALTIME, // 30 seconds for real-time collaboration
    refetchInterval: (query) => {
      const data = query.state.data;
      if (hasActiveTimelineEnrichments(data)) {
        return QUERY_REFETCH_INTERVALS.ENRICHMENT_ACTIVE;
      }
      if (!isConnected && data?.triage_recommendation?.status === 'QUEUED') {
        return QUERY_REFETCH_INTERVALS.TRIAGE_ACTIVE;
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
