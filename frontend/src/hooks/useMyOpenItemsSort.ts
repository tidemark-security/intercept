import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";

import type { RecentItem } from "@/types/generated/models/RecentItem";
import { AlertsService } from "@/types/generated/services/AlertsService";
import { CasesService } from "@/types/generated/services/CasesService";
import { TasksService } from "@/types/generated/services/TasksService";

export type MyOpenItem = RecentItem & {
  created_at?: string | null;
};

export type MyOpenItemsSortKey = "human_id" | "title" | "item_type" | "status" | "priority" | "age";
export type MyOpenItemsSortDirection = "asc" | "desc";

export interface MyOpenItemsSortState {
  key: MyOpenItemsSortKey;
  direction: MyOpenItemsSortDirection;
}

const CREATED_AT_STALE_TIME_MS = 5 * 60 * 1000;

const DEFAULT_SORT: MyOpenItemsSortState = {
  key: "priority",
  direction: "desc",
};

const DEFAULT_DIRECTION_BY_KEY: Record<MyOpenItemsSortKey, MyOpenItemsSortDirection> = {
  human_id: "asc",
  title: "asc",
  item_type: "asc",
  status: "asc",
  priority: "desc",
  age: "asc",
};

const PRIORITY_RANK: Record<string, number> = {
  INFO: 0,
  LOW: 1,
  MEDIUM: 2,
  HIGH: 3,
  CRITICAL: 4,
  EXTREME: 5,
};

function parseTime(value: string | null | undefined): number {
  if (!value) {
    return Number.POSITIVE_INFINITY;
  }

  const time = new Date(value).getTime();
  return Number.isNaN(time) ? Number.POSITIVE_INFINITY : time;
}

function compareStrings(left: string | null | undefined, right: string | null | undefined): number {
  return (left ?? "").localeCompare(right ?? "", undefined, { numeric: true, sensitivity: "base" });
}

function comparePriority(left: MyOpenItem, right: MyOpenItem): number {
  const leftRank = PRIORITY_RANK[(left.priority ?? "INFO").toUpperCase()] ?? PRIORITY_RANK.INFO;
  const rightRank = PRIORITY_RANK[(right.priority ?? "INFO").toUpperCase()] ?? PRIORITY_RANK.INFO;

  return leftRank - rightRank;
}

function compareByKey(left: MyOpenItem, right: MyOpenItem, key: MyOpenItemsSortKey): number {
  switch (key) {
    case "human_id":
      return compareStrings(left.human_id, right.human_id);
    case "title":
      return compareStrings(left.title, right.title);
    case "item_type":
      return compareStrings(left.item_type, right.item_type);
    case "status":
      return compareStrings(left.status, right.status);
    case "priority":
      return comparePriority(left, right);
    case "age":
      return parseTime(left.created_at) - parseTime(right.created_at);
  }
}

function getItemKey(item: Pick<MyOpenItem, "item_type" | "id">): string {
  return `${item.item_type}-${item.id}`;
}

async function fetchCreatedAt(item: Pick<MyOpenItem, "item_type" | "id">): Promise<string | null> {
  switch (item.item_type) {
    case "alert": {
      const alert = await AlertsService.getAlertApiV1AlertsAlertIdGet({
        alertId: item.id,
        includeLinkedTimelines: false,
      });
      return alert.created_at;
    }
    case "case": {
      const caseItem = await CasesService.getCaseApiV1CasesCaseIdGet({
        caseId: item.id,
        includeLinkedTimelines: false,
      });
      return caseItem.created_at;
    }
    case "task": {
      const task = await TasksService.getTaskApiV1TasksTaskIdGet({
        taskId: item.id,
        includeLinkedTimelines: false,
      });
      return task.created_at;
    }
  }

  return null;
}

export function formatOpenItemAge(createdAt: string | null | undefined, now: Date = new Date()): string {
  if (!createdAt) {
    return "Unknown";
  }

  const createdTime = new Date(createdAt).getTime();
  const nowTime = now.getTime();

  if (Number.isNaN(createdTime) || Number.isNaN(nowTime)) {
    return "Unknown";
  }

  const ageMs = Math.max(0, nowTime - createdTime);
  const minutes = Math.floor(ageMs / 60000);

  if (minutes < 1) {
    return "<1m";
  }

  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h`;
  }

  const days = Math.floor(hours / 24);
  if (days < 30) {
    return `${days}d`;
  }

  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months}mo`;
  }

  return `${Math.floor(days / 365)}y`;
}

export function sortMyOpenItems(items: MyOpenItem[], sort: MyOpenItemsSortState): MyOpenItem[] {
  const directionMultiplier = sort.direction === "asc" ? 1 : -1;

  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const primary = compareByKey(left.item, right.item, sort.key) * directionMultiplier;
      if (primary !== 0) {
        return primary;
      }

      const fallback = compareByKey(left.item, right.item, DEFAULT_SORT.key) * -1;
      return fallback || left.index - right.index;
    })
    .map(({ item }) => item);
}

export function getNextMyOpenItemsSort(
  currentSort: MyOpenItemsSortState,
  key: MyOpenItemsSortKey,
): MyOpenItemsSortState {
  if (currentSort.key !== key) {
    return {
      key,
      direction: DEFAULT_DIRECTION_BY_KEY[key],
    };
  }

  return {
    key,
    direction: currentSort.direction === "asc" ? "desc" : "asc",
  };
}

export function useMyOpenItemsWithCreatedAt(items: MyOpenItem[] = []) {
  const queries = useQueries({
    queries: items.map((item) => ({
      queryKey: ["dashboard", "my-open-items", "created-at", item.item_type, item.id],
      queryFn: () => fetchCreatedAt(item),
      enabled: !item.created_at,
      staleTime: CREATED_AT_STALE_TIME_MS,
    })),
  });

  return useMemo(() => {
    const createdAtByItemKey = new Map<string, string | null>();

    queries.forEach((query, index) => {
      const item = items[index];
      if (item) {
        createdAtByItemKey.set(getItemKey(item), typeof query.data === "string" ? query.data : null);
      }
    });

    return items.map((item) => ({
      ...item,
      created_at: item.created_at ?? createdAtByItemKey.get(getItemKey(item)) ?? null,
    }));
  }, [items, queries]);
}

export function useMyOpenItemsSort(items: MyOpenItem[] = []) {
  const [sort, setSort] = useState<MyOpenItemsSortState>(DEFAULT_SORT);

  const sortedItems = useMemo(() => sortMyOpenItems(items, sort), [items, sort]);

  const requestSort = (key: MyOpenItemsSortKey) => {
    setSort((currentSort) => getNextMyOpenItemsSort(currentSort, key));
  };

  return {
    sort,
    sortedItems,
    requestSort,
  };
}
