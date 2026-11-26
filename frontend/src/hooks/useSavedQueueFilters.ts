import { useQuery, type QueryClient } from "@tanstack/react-query";
import type { SavedFilterQueue } from "@/types/generated/models/SavedFilterQueue";
import { SavedFiltersService } from "@/types/generated/services/SavedFiltersService";
import { sidebarBadgeCountsKey } from "./useDashboard";

function savedFilterKey(queue: SavedFilterQueue, userId: string) {
  return ["saved-filters", userId, queue] as const;
}

export function useSavedQueueFilters(queue: SavedFilterQueue, userId: string) {
  return useQuery({
    queryKey: savedFilterKey(queue, userId),
    queryFn: () => SavedFiltersService.listSavedFilters({ queue }),
    staleTime: 0,
  });
}

export function invalidateSavedQueueFilters(queryClient: QueryClient, queue: SavedFilterQueue, userId: string) {
  void queryClient.invalidateQueries({ queryKey: savedFilterKey(queue, userId) });
  if (queue === "alerts") {
    void queryClient.invalidateQueries({ queryKey: sidebarBadgeCountsKey });
  }
}
