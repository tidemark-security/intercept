import { describe, expect, it } from 'vitest';

import type { TimelineItem } from '@/types/timeline';
import { groupTimelineItems } from './timelineUtils';

describe('groupTimelineItems', () => {
  it('does not group tombstones with normal items that share a timestamp', () => {
    const normalItem = {
      id: 'normal-note',
      type: 'note',
      timestamp: '2026-01-01T12:00:00Z',
      created_at: '2026-01-01T12:00:00Z',
      created_by: 'analyst',
      description: '',
      flagged: false,
      highlighted: false,
      replies: null,
    } as TimelineItem;
    const deletedItem = {
      id: 'deleted-note',
      type: '_deleted',
      deleted_at: '2026-01-03T12:00:00Z',
      deleted_by: 'admin',
      original_type: 'note',
      original_timestamp: '2026-01-01T12:00:00Z',
      original_created_at: '2026-01-01T12:00:00Z',
      original_created_by: 'analyst',
      created_at: '2026-01-01T12:00:00Z',
      description: '',
      flagged: false,
      highlighted: false,
      replies: null,
    } as TimelineItem;

    const groups = groupTimelineItems([normalItem, deletedItem]);

    expect(groups).toHaveLength(2);
    expect(groups.map((group) => group.items.map((item) => item.id))).toEqual([
      ['normal-note'],
      ['deleted-note'],
    ]);
  });
});