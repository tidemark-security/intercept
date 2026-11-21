import type { FilterState } from '@/types/filters';

type EntityListFilterState<Status> = Omit<FilterState, 'status'> & { status: Status[] | null };

export function toEntityListQueryFilters<Status>(filters: EntityListFilterState<Status>) {
  return {
    status: filters.status,
    // Selection order does not affect results or the query cache key.
    assignee: filters.assignee?.length ? [...new Set(filters.assignee)].sort() : null,
    includeTags: filters.includeTags ?? null,
    excludeTags: filters.excludeTags ?? null,
    search: filters.search || null,
    startDate: filters.dateRange?.start || null,
    endDate: filters.dateRange?.end || null,
    sortBy: filters.sortBy ?? 'created_at',
    sortOrder: filters.sortOrder ?? 'desc',
  };
}
