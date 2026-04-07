/**
 * Helper functions for timeline operations
 */

import type { TimelineItem } from '@/types/timeline';
import { findTimelineItem, type TimelineItemMap } from './timelineUtils';

function sortTimelineItems(items: TimelineItem[]): TimelineItem[] {
  return items.sort((left, right) => {
    const leftKey = left.timestamp || left.created_at || '';
    const rightKey = right.timestamp || right.created_at || '';
    return leftKey.localeCompare(rightKey);
  });
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
