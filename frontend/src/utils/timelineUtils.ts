/**
 * Utility functions for timeline operations
 */

import type { TimelineItem } from '@/types/timeline';
import type { TimelineItemType } from '@/types/drafts';

/**
 * Recursively find a timeline item by ID
 * Searches through nested replies to find matching item
 * 
 * @param items Array of timeline items to search
 * @param itemId ID of the item to find
 * @returns Found item or null if not found
 */
export function findTimelineItem(
  items: TimelineItem[],
  itemId: string
): TimelineItem | null {
  for (const item of items) {
    if (item.id === itemId) return item;
    
    const replies = item.replies as TimelineItem[] | null | undefined;
    if (replies && Array.isArray(replies)) {
      const found = findTimelineItem(replies, itemId);
      if (found) return found;
    }
  }
  return null;
}

/**
 * Recursively update a timeline item by ID
 * Returns a new array with the updated item (immutable operation)
 * 
 * @param items Array of timeline items to update
 * @param itemId ID of the item to update
 * @param updates Partial updates to apply to the item
 * @returns New array with the updated item
 */
export function updateTimelineItemById(
  items: TimelineItem[],
  itemId: string,
  updates: Partial<TimelineItem>
): TimelineItem[] {
  return items.map((item): TimelineItem => {
    if (item.id === itemId) {
      return { ...item, ...updates } as TimelineItem;
    }
    const replies = item.replies as TimelineItem[] | null | undefined;
    if (replies && Array.isArray(replies) && replies.length > 0) {
      return {
        ...item,
        replies: updateTimelineItemById(replies, itemId, updates),
      } as TimelineItem;
    }
    return item;
  });
}

/**
 * Recursively remove a timeline item by ID
 * Returns a new array without the removed item (immutable operation)
 * 
 * @param items Array of timeline items
 * @param itemId ID of the item to remove
 * @returns New array without the removed item
 */
export function removeTimelineItemById(
  items: TimelineItem[],
  itemId: string
): TimelineItem[] {
  return items
    .filter(item => item.id !== itemId)
    .map((item): TimelineItem => {
      const replies = item.replies as TimelineItem[] | null | undefined;
      if (replies && Array.isArray(replies) && replies.length > 0) {
        return {
          ...item,
          replies: removeTimelineItemById(replies, itemId),
        } as TimelineItem;
      }
      return item;
    });
}

/**
 * Create an optimistic timeline item for immediate UI feedback
 * Used for optimistic updates before server response
 * 
 * @param payload Partial timeline item data
 * @param currentUser Optional current user name (defaults to 'You')
 * @returns Complete timeline item for optimistic display
 */
export function createOptimisticTimelineItem(
  payload: Partial<TimelineItem>,
  currentUser?: string
): TimelineItem {
  return {
    id: payload.id || `temp-${Date.now()}`,
    type: payload.type || 'note',
    description: payload.description || '',
    timestamp: payload.timestamp || new Date().toISOString(),
    created_at: new Date().toISOString(),
    created_by: currentUser || 'You',
    tags: 'tags' in payload ? (payload.tags || []) : [],
    flagged: payload.flagged || false,
    highlighted: payload.highlighted || false,
    replies: null,
    ...payload,
  } as TimelineItem;
}

/**
 * Map backend timeline item types to dock types
 * Handles type normalization for the dock interface
 * 
 * @param backendType Timeline item type from backend
 * @returns Normalized type for dock
 */
export function mapItemTypeToDockType(backendType: string): TimelineItemType {
  // Handle actor types - consolidate 3 backend types into single dock type
  if (
    backendType === 'internal_actor' ||
    backendType === 'external_actor' ||
    backendType === 'threat_actor'
  ) {
    return 'actor';
  }
  
  return backendType as TimelineItemType;
}
