import { MIN_SEARCH_QUERY_LENGTH } from "@/components/search/searchUtils";

export const MAX_QUEUE_SEARCH_LENGTH = 200;

export function normalizeQueueSearch(value: string) {
  const query = value.trim().replace(/\s+/g, " ");
  return query.length >= MIN_SEARCH_QUERY_LENGTH && query.length <= MAX_QUEUE_SEARCH_LENGTH ? query : "";
}
