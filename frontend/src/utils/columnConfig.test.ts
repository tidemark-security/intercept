import { describe, expect, it } from 'vitest';

import { getColumnConfig } from '@/utils/columnConfig';

describe('getColumnConfig', () => {
  it('uses the persisted list width in split mode', () => {
    expect(getColumnConfig(null, 768).desktop!.leftWidth).toBe('shrink-0');
  });

  it('lets the left column fill available width in left-only mode', () => {
    expect(getColumnConfig(null, 768, true).desktop!.leftWidth).toBe('w-full');
    expect(getColumnConfig(null, 768, true).tablet!.leftWidth).toBe('w-full');
    expect(getColumnConfig(null, 768, true).ultrawide!.leftWidth).toBe('w-full');
  });
});
