import { describe, expect, it } from 'vitest';

import { hasActiveTimelineEnrichments, isEnrichmentStatusActive } from './enrichmentState';

describe('enrichmentState', () => {
  it('detects active enrichment statuses', () => {
    expect(isEnrichmentStatusActive('pending')).toBe(true);
    expect(isEnrichmentStatusActive('in_progress')).toBe(true);
    expect(isEnrichmentStatusActive('complete')).toBe(false);
    expect(isEnrichmentStatusActive('failed')).toBe(false);
  });

  it('detects active enrichments in nested timeline replies', () => {
    expect(
      hasActiveTimelineEnrichments({
        timeline_items: {
          'item-1': {
            enrichment_status: 'complete',
            replies: {
              'reply-1': {
                enrichment_status: 'pending',
              },
            },
          },
        },
      }),
    ).toBe(true);
  });

  it('returns false when no timeline item is actively enriching', () => {
    expect(
      hasActiveTimelineEnrichments({
        timeline_items: {
          'item-1': { enrichment_status: 'complete' },
          'item-2': { enrichment_status: 'failed' },
        },
      }),
    ).toBe(false);
  });
});