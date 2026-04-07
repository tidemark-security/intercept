/**
 * Utility functions for timeline operations
 */

import type { TimelineItem } from '@/types/timeline';
import type { TimelineItemType } from '@/types/drafts';

export type TimelineItemMap = Record<string, TimelineItem>;
export type TimelineItemCollection = TimelineItem[] | TimelineItemMap | null | undefined;

function toCollectionArray(items: TimelineItemCollection): TimelineItem[] {
  if (Array.isArray(items)) {
    return items;
  }
  if (items && typeof items === 'object') {
    return Object.values(items).sort((left, right) => {
      const leftKey = left.timestamp || left.created_at || '';
      const rightKey = right.timestamp || right.created_at || '';
      return leftKey.localeCompare(rightKey);
    });
  }
  return [];
}

/**
 * Recursively find a timeline item by ID
 * Searches through nested replies to find matching item
 * 
 * @param items Array of timeline items to search
 * @param itemId ID of the item to find
 * @returns Found item or null if not found
 */
export function findTimelineItem(
  items: TimelineItemCollection,
  itemId: string
): TimelineItem | null {
  for (const item of toCollectionArray(items)) {
    if (item.id === itemId) return item;
    
    const replies = item.replies;
    if (replies) {
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
  items: TimelineItemCollection,
  itemId: string,
  updates: Partial<TimelineItem>
) : TimelineItemCollection {
  if (Array.isArray(items)) {
    return items.map((item): TimelineItem => {
      if (item.id === itemId) {
        return { ...item, ...updates } as TimelineItem;
      }
      const replies = item.replies;
      if (replies) {
        return {
          ...item,
          replies: updateTimelineItemById(replies, itemId, updates) as TimelineItemMap,
        } as TimelineItem;
      }
      return item;
    });
  }

  if (!items || typeof items !== 'object') {
    return items;
  }

  let changed = false;
  const nextItems: TimelineItemMap = {};

  for (const [key, item] of Object.entries(items)) {
    let nextItem = item;
    if (item.id === itemId) {
      nextItem = { ...item, ...updates } as TimelineItem;
      changed = true;
    }
    const replies = item.replies;
    if (replies) {
      const nextReplies = updateTimelineItemById(replies, itemId, updates) as TimelineItemMap;
      if (nextReplies !== replies) {
        nextItem = { ...nextItem, replies: nextReplies } as TimelineItem;
        changed = true;
      }
    }
    nextItems[key] = nextItem;
  }

  return changed ? nextItems : items;
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
  items: TimelineItemCollection,
  itemId: string
): TimelineItemCollection {
  if (Array.isArray(items)) {
    return items
      .filter(item => item.id !== itemId)
      .map((item): TimelineItem => {
        const replies = item.replies;
        if (replies) {
          return {
            ...item,
            replies: removeTimelineItemById(replies, itemId) as TimelineItemMap,
          } as TimelineItem;
        }
        return item;
      });
  }

  if (!items || typeof items !== 'object') {
    return items;
  }

  let changed = false;
  const nextItems: TimelineItemMap = {};
  for (const [key, item] of Object.entries(items)) {
    if (item.id === itemId) {
      changed = true;
      continue;
    }

    let nextItem = item;
    const replies = item.replies;
    if (replies) {
      const nextReplies = removeTimelineItemById(replies, itemId) as TimelineItemMap;
      if (nextReplies !== replies) {
        nextItem = { ...item, replies: nextReplies } as TimelineItem;
        changed = true;
      }
    }
    nextItems[key] = nextItem;
  }

  return changed ? nextItems : items;
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
