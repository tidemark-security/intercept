import { describe, expect, it } from 'vitest';

import {
  canShowSplitPaneCenter,
  getSplitPaneCenterWidth,
  MIN_SPLIT_CENTER_WIDTH,
} from '@/hooks/useSplitPaneCenter';

describe('split pane center width helpers', () => {
  it('computes the remaining center pane width after fixed split-pane chrome', () => {
    expect(getSplitPaneCenterWidth(1502, 768)).toBe(MIN_SPLIT_CENTER_WIDTH);
    expect(getSplitPaneCenterWidth(1501, 768)).toBe(MIN_SPLIT_CENTER_WIDTH - 1);
  });

  it('shows the split center only when non-mobile and at least 600px remains', () => {
    expect(canShowSplitPaneCenter(1502, 768, 'desktop')).toBe(true);
    expect(canShowSplitPaneCenter(1501, 768, 'desktop')).toBe(false);
    expect(canShowSplitPaneCenter(1502, 768, 'tablet')).toBe(true);
    expect(canShowSplitPaneCenter(2000, 768, 'mobile')).toBe(false);
  });
});

