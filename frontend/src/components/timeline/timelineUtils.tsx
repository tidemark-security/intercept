import React from 'react';
import { Tag } from '@/components/data-display/Tag';
import type { TimelineItem } from '@/types/timeline';
import { isEnrichmentStatusActive } from '@/utils/enrichmentState';

const FAILED_ENRICHMENT_STATUSES = new Set(['failed']);

/**
 * Shared utility functions for timeline rendering
 * Extracted from AlertTimeline.tsx as the authoritative implementation
 */

/**
 * Represents a group of timeline items that share the same timestamp and description
 */
export interface TimelineItemGroup {
  /** The primary item representing the group (first item in the group) */
  item: TimelineItem;
  /** All items in this group (including the primary item) */
  items: TimelineItem[];
  /** Index of this group in the original array */
  index: number;
}

/**
 * Groups timeline items by timestamp and description
 * 
 * Items with identical timestamps and descriptions are collapsed into a single
 * timeline entry with multiple cards displayed within it.
 * 
 * Grouping rules:
 * - Items with timestamps within 1 second of each other AND same type AND both have null/empty descriptions are grouped
 * - Items with same timestamp AND same description (when descriptions exist) are grouped
 *   (This handles attachments uploaded at the same time)
 * - Items must have matching flag/highlight status to be grouped together
 *   (A highlighted item will be in a separate group from non-highlighted items)
 * 
 * @param items - Timeline items to group
 * @returns Array of timeline item groups
 * 
 * @example
 * ```tsx
 * const groups = groupTimelineItems(timelineItems);
 * groups.forEach((group, index) => {
 *   // group.item - primary item for the group
 *   // group.items - all items in the group (for rendering multiple cards)
 *   // group.index - original index in timeline
 * });
 * ```
 */
export function groupTimelineItems(items: TimelineItem[]): TimelineItemGroup[] {
  if (!items || items.length === 0) return [];

  const groups: TimelineItemGroup[] = [];
  const processedIndices = new Set<number>();

  items.forEach((item, index) => {
    // Skip if already processed as part of a group
    if (processedIndices.has(index)) return;

    // Find all items with similar timestamp and description (or same timestamp/type if no descriptions)
    const matchingItems = items.filter((otherItem, otherIndex) => {
      if (otherIndex < index) return false; // Only look ahead
      if (!item.created_at || !otherItem.created_at) return false;
      
      // Calculate timestamp difference in milliseconds
      const itemTime = new Date(item.created_at).getTime();
      const otherTime = new Date(otherItem.created_at).getTime();
      const timeDiffMs = Math.abs(itemTime - otherTime);
      
      // Must be within 1 second (1000ms)
      const withinTimeWindow = timeDiffMs <= 1000;
      if (!withinTimeWindow) return false;
      
      // Must have matching flag and highlight status
      if (item.flagged !== otherItem.flagged || item.highlighted !== otherItem.highlighted) {
        return false;
      }
      
      // Check if both have empty/null descriptions
      const itemHasNoDescription = !item.description || item.description.trim() === '';
      const otherHasNoDescription = !otherItem.description || otherItem.description.trim() === '';
      
      if (itemHasNoDescription && otherHasNoDescription) {
        // Both have no description - group by timestamp window + type
        return item.type === otherItem.type;
      } else {
        // At least one has a description - must match exactly AND be within time window
        return item.description === otherItem.description && withinTimeWindow;
      }
    });

    // Mark all matching items as processed
    matchingItems.forEach((_, matchIndex) => {
      const actualIndex = items.indexOf(matchingItems[matchIndex]);
      processedIndices.add(actualIndex);
    });

    // Create group with primary item and all matching items
    groups.push({
      item: item,
      items: matchingItems.length > 1 ? matchingItems : [item],
      index: index,
    });
  });

  return groups;
}

/**
 * Renders tags as small badges
 * 
 * Handles both string (semicolon-separated) and array formats
 * 
 * @param tags - Tags to render (string, array, or null/undefined)
 * @returns React node with rendered tags or null
 * 
 * @example
 * ```tsx
 * {renderTags(item.tags)}
 * {renderTags("malware;phishing;critical")}
 * {renderTags(["malware", "phishing", "critical"])}
 * ```
 */
export function renderTags(tags: string | string[] | undefined | null): React.ReactNode {
  if (!tags) return null;

  // Handle both string (semicolon-separated) and array formats
  const tagList = Array.isArray(tags)
    ? tags
    : typeof tags === 'string'
    ? tags.split(';').map((t) => t.trim()).filter(Boolean)
    : [];

  if (tagList.length === 0) return null;

  return (
    <div className="flex w-full flex-wrap items-center gap-2">
      {tagList.map((tag, index) => (
        <Tag
          key={`${tag}-${index}`}
          tagText={tag}
          showDelete={false}
          p="0"
        />
      ))}
    </div>
  );
}

export function isTimelineItemEnrichmentActive(item: TimelineItem): boolean {
  return isEnrichmentStatusActive(item.enrichment_status);
}

export function isTimelineItemEnrichmentFailed(item: TimelineItem): boolean {
  const status = item.enrichment_status?.trim().toLowerCase();

  return status ? FAILED_ENRICHMENT_STATUSES.has(status) : false;
}

export function isTimelineItemEnrichable(item: TimelineItem): boolean {
  const itemType = item.type;

  if (itemType === 'internal_actor') {
    const identifierFields = [
      (item as TimelineItem & { user_id?: string | null }).user_id,
      (item as TimelineItem & { contact_email?: string | null }).contact_email,
      (item as TimelineItem & { name?: string | null }).name,
    ];

    return identifierFields.some((value) => typeof value === 'string' && value.trim().length > 0);
  }

  if (itemType === 'observable') {
    const observableType = String((item as TimelineItem & { observable_type?: string | null }).observable_type || '').trim().toUpperCase();
    const observableValue = String((item as TimelineItem & { observable_value?: string | null }).observable_value || '').trim();
    return observableType === 'IP' && observableValue.length > 0;
  }

  if (itemType === 'system') {
    const ipAddress = String((item as TimelineItem & { ip_address?: string | null }).ip_address || '').trim();
    return ipAddress.length > 0;
  }

  if (itemType === 'network_traffic') {
    const sourceIp = String((item as TimelineItem & { source_ip?: string | null }).source_ip || '').trim();
    const destinationIp = String((item as TimelineItem & { destination_ip?: string | null }).destination_ip || '').trim();
    return sourceIp.length > 0 || destinationIp.length > 0;
  }

  return false;
}

/**
 * Auto-scroll hook for timeline items
 * 
 * Implements retry mechanism to ensure DOM has updated before scrolling.
 * Extracted from AlertTimeline.tsx useEffect logic.
 * 
 * @param scrollToItemId - ID of the timeline item to scroll to
 * @param entityDetail - Entity detail object (alert or case) to trigger on changes
 * @param enabled - Whether auto-scroll is enabled (defaults to true)
 * 
 * @example
 * ```tsx
 * useAutoScrollToTimelineItem(scrollToItemId, alertDetail);
 * useAutoScrollToTimelineItem(scrollToItemId, caseDetail, isEditable);
 * ```
 */
export function useAutoScrollToTimelineItem(
  scrollToItemId: string | null | undefined,
  entityDetail: any,
  enabled: boolean = true
): void {
  React.useEffect(() => {
    if (scrollToItemId && entityDetail && enabled) {
      // Retry mechanism to ensure DOM has updated
      let attempts = 0;
      const maxAttempts = 10; // Try for up to 1 second
      
      const tryScroll = () => {
        const element = document.getElementById(`timeline-item-${scrollToItemId}`);
        if (element) {
          console.log('Scrolling to timeline item:', scrollToItemId);
          element.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center',
            inline: 'nearest'
          });
        } else {
          attempts++;
          if (attempts < maxAttempts) {
            console.log(`Retry scroll attempt ${attempts}/${maxAttempts} for:`, scrollToItemId);
            setTimeout(tryScroll, 100);
          } else {
            console.warn('Failed to find timeline item after', maxAttempts, 'attempts:', scrollToItemId);
          }
        }
      };
      
      // Initial delay to let React render
      setTimeout(tryScroll, 100);
    }
  }, [entityDetail, scrollToItemId, enabled]);
}
