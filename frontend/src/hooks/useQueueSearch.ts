import { useQuery } from "@tanstack/react-query";
import { SearchService } from "@/types/generated/services/SearchService";
import type { QueueSearchRow } from "@/types/generated/models/QueueSearchRow";
import { QUERY_REFETCH_INTERVALS, QUERY_REFETCH_INTERVALS_WS, QUERY_STALE_TIMES } from "@/config/queryConfig";
import { useWebSocket } from "@/contexts/WebSocketContext";
import { toEntityListQueryFilters } from "@/utils/entityListQueryFilters";
import { normalizeQueueSearch } from "@/utils/queueSearch";
import { getQueueSearchQueryKey, type EntityType } from "./queryKeys";

type QueueSearchRequest = Parameters<typeof SearchService.queueSearchApiV1SearchQueueGet>[0];
export type QueueListRow = Omit<QueueSearchRow, "tags"> & {
  tags?: string[] | null;
  description?: string | null;
};

const queueSorts = new Set(["created_at", "updated_at", "priority", "status"]);

export function useQueueSearch(
  entityType: EntityType,
  filters: Parameters<typeof toEntityListQueryFilters<string>>[0],
  page: number,
  size: number,
) {
  const { isConnected } = useWebSocket();
  const { search, sortBy, ...listFilters } = toEntityListQueryFilters(filters);
  const query = normalizeQueueSearch(search ?? "");
  const request: QueueSearchRequest = {
    ...listFilters,
    q: query,
    sortBy: queueSorts.has(sortBy) ? sortBy as QueueSearchRequest["sortBy"] : "created_at",
    entityType,
    skip: (page - 1) * size,
    limit: size,
  };
  return useQuery({
    enabled: !!query,
    queryKey: [...getQueueSearchQueryKey(entityType), request],
    queryFn: async ({ signal }) => {
      const pending = SearchService.queueSearchApiV1SearchQueueGet(request);
      const cancel = () => pending.cancel();
      if (signal.aborted) cancel();
      else signal.addEventListener("abort", cancel, { once: true });
      try {
        const response = await pending;
        return {
          items: response.results,
          total: response.total,
          pages: Math.ceil(response.total / size),
        };
      } finally {
        signal.removeEventListener("abort", cancel);
      }
    },
    staleTime: QUERY_STALE_TIMES.LIST,
    retry: false,
    refetchInterval: isConnected ? QUERY_REFETCH_INTERVALS_WS.LIST : QUERY_REFETCH_INTERVALS.LIST,
    refetchIntervalInBackground: false,
  });
}
