import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { DashboardService } from '@/types/generated/services/DashboardService';
import type { DashboardStatsResponse } from '@/types/generated/models/DashboardStatsResponse';
import type { RecentItemsResponse } from '@/types/generated/models/RecentItemsResponse';

interface UseDashboardOptions {
  myItems?: boolean;
}

interface UseRecentItemsOptions {
  myItems?: boolean;
  limit?: number;
}

interface UsePriorityItemsOptions {
  limit?: number;
}

/**
 * Hook to fetch dashboard statistics from the API using TanStack Query
 * Provides caching, automatic refetching, and loading/error states
 */
export function useDashboard(
  options: UseDashboardOptions = {}
): UseQueryResult<DashboardStatsResponse, Error> {
  const { myItems = true } = options;

  return useQuery({
    queryKey: ['dashboard', 'stats', { myItems }],
    queryFn: () => DashboardService.getDashboardStatsApiV1DashboardStatsGet({ myItems }),
    staleTime: 30 * 1000, // 30 seconds - dashboard stats should be fresh
    refetchInterval: 60 * 1000, // Refetch every minute
  });
}

/**
 * Hook to fetch recent items from the API using TanStack Query
 */
export function useRecentItems(
  options: UseRecentItemsOptions = {}
): UseQueryResult<RecentItemsResponse, Error> {
  const { myItems = true, limit = 10 } = options;

  return useQuery({
    queryKey: ['dashboard', 'recent', { myItems, limit }],
    queryFn: () => DashboardService.getRecentItemsApiV1DashboardRecentGet({ myItems, limit }),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}

/**
 * Hook to fetch open items assigned to current user (My Open Items)
 * Returns all open alerts, cases, and tasks sorted by priority then type
 */
export function usePriorityItems(
  options: UsePriorityItemsOptions = {}
): UseQueryResult<RecentItemsResponse, Error> {
  const { limit = 10 } = options;

  return useQuery({
    queryKey: ['dashboard', 'priority', { limit }],
    queryFn: () => DashboardService.getPriorityItemsApiV1DashboardPriorityItemsGet({ limit }),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}
