import { useQuery } from '@tanstack/react-query';

import { QUERY_REFETCH_INTERVALS, QUERY_STALE_TIMES } from '@/config/queryConfig';
import type { QueueJobsPage } from '@/types/generated/models/QueueJobsPage';
import { AdminService } from '@/types/generated/services/AdminService';

export interface UseQueueJobsParams {
  page?: number;
  size?: number;
  entrypoint?: string | null;
  status?: string | null;
  startDate?: string | null;
  endDate?: string | null;
}

export function useQueueJobs({
  page = 1,
  size = 25,
  entrypoint = null,
  status = null,
  startDate = null,
  endDate = null,
}: UseQueueJobsParams = {}) {
  return useQuery<QueueJobsPage, Error>({
    queryKey: ['queue-jobs', { page, size, entrypoint, status, startDate, endDate }],
    queryFn: async () => {
      const response = await AdminService.getQueueJobsApiV1AdminQueueJobsGet({
        page,
        size,
        entrypoint: entrypoint || undefined,
        status: status || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      });

      return response as QueueJobsPage;
    },
    staleTime: QUERY_STALE_TIMES.LIST,
    refetchInterval: QUERY_REFETCH_INTERVALS.LIST,
    refetchIntervalInBackground: false,
  });
}
