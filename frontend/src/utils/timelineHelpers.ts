/**
 * Helper functions for timeline operations
 */

import type { TimelineItem } from '@/types/timeline';
import { findTimelineItem } from './timelineUtils';

/**
 * Get timeline items from alert detail with proper type casting
 * Handles the type assertion in one place
 */
export function getTimelineItems(alertDetail: { timeline_items?: unknown } | null): TimelineItem[] | null {
  if (!alertDetail) return null;
  return alertDetail.timeline_items as unknown as TimelineItem[] | null;
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
  const item = timelineItems ? findTimelineItem(timelineItems, itemId) : null;
  return item?.[property] ?? false;
}
