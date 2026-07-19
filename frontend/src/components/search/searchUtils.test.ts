import { describe, expect, it } from 'vitest';

import { mapState } from './searchUtils';

describe('mapState', () => {
  it('maps raw closed alert statuses to closed', () => {
    expect(mapState('CLOSED_TP', 'alert')).toBe('closed');
    expect(mapState('CLOSED_FP', 'alert')).toBe('closed');
    expect(mapState('CLOSED_DUPLICATE', 'alert')).toBe('closed');
  });

  it('keeps task status mapping separate from alert status mapping', () => {
    expect(mapState('CLOSED_TP', 'task')).toBe('tsk_todo');
  });
});
