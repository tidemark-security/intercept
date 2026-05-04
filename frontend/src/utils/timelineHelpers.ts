/**
 * Helper functions for timeline operations
 */

import type { TimelineItem } from '@/types/timeline';
import { isDeletedItem } from '@/types/timeline';
import { findTimelineItem, type TimelineItemMap } from './timelineUtils';

type TimelineSortField = 'created_at' | 'timestamp';
type TimelineSortDirection = 'asc' | 'desc';

export function getTimelineItemSortValue(
  item: TimelineItem,
  sortBy: TimelineSortField = 'timestamp',
): string | null {
  if (isDeletedItem(item)) {
    return item.original_timestamp || item.original_created_at || item.deleted_at || null;
  }

  if (sortBy === 'created_at') {
    return item.created_at || item.timestamp || null;
  }

  return item.timestamp || item.created_at || null;
}

function toTimelineTime(value: string | null): number | null {
  if (!value) {
    return null;
  }

  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

export function compareTimelineItems(
  left: TimelineItem,
  right: TimelineItem,
  sortBy: TimelineSortField = 'timestamp',
  direction: TimelineSortDirection = 'asc',
): number {
  const leftTime = toTimelineTime(getTimelineItemSortValue(left, sortBy));
  const rightTime = toTimelineTime(getTimelineItemSortValue(right, sortBy));

  if (leftTime === null && rightTime === null) {
    return 0;
  }
  if (leftTime === null) {
    return 1;
  }
  if (rightTime === null) {
    return -1;
  }

  const comparison = leftTime - rightTime;
  return direction === 'asc' ? comparison : -comparison;
}

function sortTimelineItems(items: TimelineItem[]): TimelineItem[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => compareTimelineItems(left.item, right.item) || left.index - right.index)
    .map(({ item }) => item);
}

export function getTimelineItemMap(
  alertDetail: { timeline_items?: unknown } | null,
): TimelineItemMap {
  if (!alertDetail || !alertDetail.timeline_items || typeof alertDetail.timeline_items !== 'object') {
    return {};
  }
  if (Array.isArray(alertDetail.timeline_items)) {
    return Object.fromEntries(
      alertDetail.timeline_items
        .filter((item): item is TimelineItem => Boolean(item && typeof item === 'object' && 'id' in item))
        .map((item) => [item.id, item]),
    );
  }
  return alertDetail.timeline_items as TimelineItemMap;
}

/**
 * Get timeline items from alert detail with proper type casting
 * Handles the type assertion in one place
 */
export function getTimelineItems(alertDetail: { timeline_items?: unknown } | null): TimelineItem[] {
  const itemMap = getTimelineItemMap(alertDetail);
  return sortTimelineItems(Object.values(itemMap));
}

/**
 * Find a timeline item and get a boolean property value
 * Helper for toggle operations (flag, highlight, etc.)
 */
export function getTimelineItemProperty(
  alertDetail: { timeline_items?: unknown } | null,
  itemId: string,
  property: 'flagged' | 'highlighted'
): boolean {
  const timelineItems = getTimelineItems(alertDetail);
  const item = findTimelineItem(timelineItems, itemId);
  return item?.[property] ?? false;
}
