import { useQuery } from '@tanstack/react-query';

import { QUERY_REFETCH_INTERVALS, QUERY_STALE_TIMES } from '@/config/queryConfig';
import type { Page_AuditLogRead_ } from '@/types/generated/models/Page_AuditLogRead_';
import { AdminService } from '@/types/generated/services/AdminService';

export interface UseAuditLogsParams {
  page?: number;
  size?: number;
  eventType?: string[] | null;
  entityType?: string | null;
  entityId?: string | null;
  performedBy?: string | null;
  search?: string | null;
  startDate?: string | null;
  endDate?: string | null;
}

export function useAuditLogs({
  page = 1,
  size = 25,
  eventType = null,
  entityType = null,
  entityId = null,
  performedBy = null,
  search = null,
  startDate = null,
  endDate = null,
}: UseAuditLogsParams = {}) {
  return useQuery<Page_AuditLogRead_, Error>({
    queryKey: ['audit-logs', { page, size, eventType, entityType, entityId, performedBy, search, startDate, endDate }],
    queryFn: async () => {
      const response = await AdminService.getAuditLogsApiV1AdminAuditGet({
        page,
        size,
        eventType: eventType || undefined,
        entityType: entityType || undefined,
        entityId: entityId || undefined,
        performedBy: performedBy || undefined,
        search: search || undefined,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
      });

      return response as Page_AuditLogRead_;
    },
    staleTime: QUERY_STALE_TIMES.LIST,
    refetchInterval: QUERY_REFETCH_INTERVALS.LIST,
    refetchIntervalInBackground: false,
  });
}