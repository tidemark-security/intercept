import React from 'react';

import type { TimelineItem } from '@/types/timeline';
import { Badge } from '@/components/data-display/Badge';
import { asRecord, EnrichmentBlockSection, getNumber, getString } from './EnrichmentBlockShared';

import { GitBranch, Search } from 'lucide-react';

type CrossCasePayload = {
  observable_type?: string;
  observable_value?: string;
  queried_at?: string;
  other_case_count?: number;
  matching_cases?: Array<Record<string, unknown>>;
};

function getPayload(item: TimelineItem): CrossCasePayload | null {
  const enrichments = asRecord((item as TimelineItem & { enrichments?: unknown }).enrichments);
  const payload = asRecord(enrichments?.cross_case_observable);
  return payload as CrossCasePayload | null;
}

export function CrossCaseObservableEnrichmentBlock({ item }: { item: TimelineItem }) {
  const payload = getPayload(item);
  if (!payload) {
    return null;
  }

  const count = getNumber(payload.other_case_count) ?? 0;
  const cases = Array.isArray(payload.matching_cases) ? payload.matching_cases : [];
  const observableType = getString(payload.observable_type);
  const observableValue = getString(payload.observable_value);
  const searchHref = observableValue ? `/search?q=${encodeURIComponent(observableValue)}` : '/search';

  return (
    <EnrichmentBlockSection icon={<GitBranch className="h-4 w-4" />} title="Cross-Case Correlation">
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {observableType && <Badge variant="neutral">{observableType}</Badge>}
          {observableValue && <Badge variant="neutral">{observableValue}</Badge>}
          <Badge variant="neutral">{count} other {count === 1 ? 'case' : 'cases'}</Badge>
          <a className="inline-flex items-center gap-1 text-caption-bold font-caption-bold text-brand-primary" href={searchHref}>
            <Search className="h-3.5 w-3.5" />
            Live search
          </a>
        </div>

        {cases.length > 0 ? (
          <div className="flex flex-col gap-2">
            {cases.slice(0, 5).map((entry) => {
              const humanId = getString(entry.case_human_id) || 'Case';
              const title = getString(entry.title);
              const status = getString(entry.status);
              const priority = getString(entry.priority);
              const updatedAt = getString(entry.updated_at);

              return (
                <div key={`${humanId}-${title || ''}`} className="rounded-md border border-neutral-border bg-default-background p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-caption-bold font-caption-bold text-default-font">{humanId}</span>
                    {status && <Badge variant="neutral">{status}</Badge>}
                    {priority && <Badge variant="neutral">{priority}</Badge>}
                  </div>
                  {title && <div className="mt-1 line-clamp-1 text-body font-body text-default-font">{title}</div>}
                  {updatedAt && <div className="mt-1 text-caption font-caption text-subtext-color">Updated {new Date(updatedAt).toLocaleString()}</div>}
                </div>
              );
            })}
          </div>
        ) : null}
      </div>
    </EnrichmentBlockSection>
  );
}
