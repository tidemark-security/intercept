import { afterEach, describe, expect, it, vi } from 'vitest';

import { getTaskDueStatus } from './taskDueStatus';

describe('getTaskDueStatus', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns overdue for due dates in the past', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-04T12:00:00Z'));

    expect(getTaskDueStatus('2026-05-04T11:59:00Z', 'TODO')).toBe('overdue');
  });

  it('returns due soon for active tasks due within 24 hours', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-04T12:00:00Z'));

    expect(getTaskDueStatus('2026-05-05T11:59:00Z', 'IN_PROGRESS')).toBe('due_soon');
  });

  it('ignores completed tasks and later due dates', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-04T12:00:00Z'));

    expect(getTaskDueStatus('2026-05-04T11:59:00Z', 'DONE')).toBeNull();
    expect(getTaskDueStatus('2026-05-06T12:00:00Z', 'TODO')).toBeNull();
  });
});
