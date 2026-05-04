import { describe, expect, it } from 'vitest';

import type { TimelineItem } from '@/types/timeline';
import { compareTimelineItems, getTimelineItems } from './timelineHelpers';

describe('timelineHelpers', () => {
  it('sorts deleted items by original chronology instead of deletion time', () => {
    const earlyItem = {
      id: 'early-note',
      type: 'note',
      timestamp: '2026-01-01T12:00:00Z',
      created_at: '2026-01-01T12:00:00Z',
      created_by: 'analyst',
      description: 'Early note',
      replies: null,
    } as TimelineItem;
    const deletedMiddleItem = {
      id: 'deleted-note',
      type: '_deleted',
      deleted_at: '2026-01-04T12:00:00Z',
      deleted_by: 'admin',
      original_type: 'note',
      original_timestamp: '2026-01-02T12:00:00Z',
      original_created_at: '2026-01-02T12:00:00Z',
      original_created_by: 'analyst',
      replies: null,
    } as TimelineItem;
    const lateItem = {
      id: 'late-note',
      type: 'note',
      timestamp: '2026-01-03T12:00:00Z',
      created_at: '2026-01-03T12:00:00Z',
      created_by: 'analyst',
      description: 'Late note',
      replies: null,
    } as TimelineItem;

    const items = getTimelineItems({
      timeline_items: {
        'late-note': lateItem,
        'deleted-note': deletedMiddleItem,
        'early-note': earlyItem,
      },
    });

    expect(items.map((item) => item.id)).toEqual(['early-note', 'deleted-note', 'late-note']);
  });

  it('supports descending deleted-item comparisons by original chronology', () => {
    const firstDeleted = {
      id: 'first-deleted',
      type: '_deleted',
      deleted_at: '2026-01-10T12:00:00Z',
      deleted_by: 'admin',
      original_type: 'note',
      original_timestamp: '2026-01-01T12:00:00Z',
      original_created_by: 'analyst',
      replies: null,
    } as TimelineItem;
    const secondDeleted = {
      id: 'second-deleted',
      type: '_deleted',
      deleted_at: '2026-01-10T12:00:00Z',
      deleted_by: 'admin',
      original_type: 'note',
      original_timestamp: '2026-01-02T12:00:00Z',
      original_created_by: 'analyst',
      replies: null,
    } as TimelineItem;

    expect(compareTimelineItems(firstDeleted, secondDeleted, 'timestamp', 'desc')).toBeGreaterThan(0);
  });
});