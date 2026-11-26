import { filtersToURLParams } from "@/hooks/useURLFilters";
import type { FilterState } from "@/types/filters";
import type { SavedFilterRead } from "@/types/generated/models/SavedFilterRead";
import type { SavedFilterSnapshot } from "@/types/generated/models/SavedFilterSnapshot";
import { ALERT_STATUS_OPTIONS } from "@/utils/statusLabels";

export function savedFilterToState(snapshot: SavedFilterSnapshot, allStatuses: string[]): FilterState {
  return {
    search: snapshot.search ?? "",
    status: (snapshot.status?.length ? snapshot.status : allStatuses) as FilterState["status"],
    assignee: snapshot.assignee ?? null,
    includeTags: snapshot.include_tags ?? null,
    excludeTags: snapshot.exclude_tags ?? null,
    dateRange: snapshot.date_range
      ? { ...snapshot.date_range, preset: snapshot.date_range.preset ?? undefined }
      : null,
    sortBy: snapshot.sort_by ?? null,
    sortOrder: snapshot.sort_order ?? null,
  };
}

export function alertFilterHref(filter: SavedFilterRead) {
  const params = filtersToURLParams(savedFilterToState(filter.filters, ALERT_STATUS_OPTIONS.map(({ value }) => value)));
  if (filter.navigation_icon) params.set("saved_filter", filter.id);
  return `/alerts?${params}`;
}
