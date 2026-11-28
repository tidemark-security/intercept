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

export async function invalidateSavedQueueFilters(queryClient: QueryClient, queue: SavedFilterQueue, userId: string) {
  const refreshes = [queryClient.invalidateQueries({ queryKey: savedFilterKey(queue, userId) })];
  if (queue === "alerts") {
    refreshes.push(queryClient.invalidateQueries({ queryKey: sidebarBadgeCountsKey }));
  }
  await Promise.all(refreshes);
}
