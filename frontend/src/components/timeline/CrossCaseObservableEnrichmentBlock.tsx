import React from 'react';
import { Link } from 'react-router-dom';

import type { TimelineItem } from '@/types/timeline';
import { Badge } from '@/components/data-display/Badge';
import { Priority } from '@/components/misc/Priority';
import { State } from '@/components/misc/State';
import {
  alertStatusToUIState,
  caseStatusToUIState,
  priorityToUIPriority,
  taskStatusToUIState,
} from '@/utils/statusHelpers';
import { asRecord, EnrichmentBlockSection, getNumber, getString } from './EnrichmentBlockShared';

import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { CaseStatus } from '@/types/generated/models/CaseStatus';
import type { Priority as PriorityType } from '@/types/generated/models/Priority';
import type { TaskStatus } from '@/types/generated/models/TaskStatus';
import { Bell, CheckSquare, GitBranch, NotebookPen, Search } from 'lucide-react';

type CrossCasePayload = {
  observable_type?: string;
  observable_value?: string;
  queried_at?: string;
  max_lookback_days?: number;
  lookback_started_at?: string;
  match_count?: number;
  matches?: Array<Record<string, unknown>>;
  correlations?: Array<Record<string, unknown>>;
};

function getPayload(item: TimelineItem): CrossCasePayload | null {
  const enrichments = asRecord((item as TimelineItem & { enrichments?: unknown }).enrichments);
  const payload = asRecord(enrichments?.cross_case_observable);
  return payload as CrossCasePayload | null;
}

function getEntityIcon(entityType?: string) {
  switch (entityType) {
    case 'alert':
      return <Bell className="h-3.5 w-3.5 text-subtext-color" />;
    case 'case':
      return <NotebookPen className="h-3.5 w-3.5 text-subtext-color" />;
    case 'task':
      return <CheckSquare className="h-3.5 w-3.5 text-subtext-color" />;
    default:
      return null;
  }
}

function getEntityHref(entityType?: string, humanId?: string) {
  if (!humanId) {
    return undefined;
  }
  switch (entityType) {
    case 'alert':
      return `/alerts/${humanId}`;
    case 'case':
      return `/cases/${humanId}`;
    case 'task':
      return `/tasks/${humanId}`;
    default:
      return undefined;
  }
}

function getStateValue(entityType?: string, status?: string): React.ComponentProps<typeof State>['state'] | null {
  if (!status) {
    return null;
  }
  if (entityType === 'alert') {
    return alertStatusToUIState(status as AlertStatus) as React.ComponentProps<typeof State>['state'];
  }
  if (entityType === 'case') {
    return caseStatusToUIState(status as CaseStatus) as React.ComponentProps<typeof State>['state'];
  }
  if (entityType === 'task') {
    return taskStatusToUIState(status as TaskStatus) as React.ComponentProps<typeof State>['state'];
  }
  return null;
}

function getCorrelationEntries(payload: CrossCasePayload): Array<Record<string, unknown>> {
  if (Array.isArray(payload.correlations) && payload.correlations.length > 0) {
    return payload.correlations;
  }
  return [payload as Record<string, unknown>];
}

export function CrossCaseObservableEnrichmentBlock({ item }: { item: TimelineItem }) {
  const payload = getPayload(item);
  if (!payload) {
    return null;
  }

  const count = getNumber(payload.match_count) ?? 0;
  const correlations = getCorrelationEntries(payload);

  return (
    <EnrichmentBlockSection icon={<GitBranch className="h-4 w-4" />} title="Observable Correlation">
      <div className="flex flex-col gap-3">
        {correlations.map((correlation, correlationIndex) => {
          const correlationObservableType = getString(correlation.observable_type);
          const correlationObservableValue = getString(correlation.observable_value);
          const correlationCount = getNumber(correlation.match_count) ?? count;
          const correlationMatches = Array.isArray(correlation.matches) ? correlation.matches : [];
          const lookbackDays = getNumber(correlation.max_lookback_days) ?? getNumber(payload.max_lookback_days);
          const searchHref = correlationObservableValue ? `/search?q=${encodeURIComponent(correlationObservableValue)}` : '/search';

          return (
            <div
              key={`${correlationObservableType || 'observable'}-${correlationObservableValue || correlationIndex}`}
              className="flex flex-col gap-3 rounded-md border border-neutral-border bg-default-background p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                {correlationObservableType && <Badge variant="neutral">{correlationObservableType}</Badge>}
                {correlationObservableValue && <Badge variant="neutral">{correlationObservableValue}</Badge>}
                <Badge variant="neutral">{correlationCount} {correlationCount === 1 ? 'match' : 'matches'}</Badge>
                {lookbackDays ? <Badge variant="neutral">{lookbackDays}d lookback</Badge> : null}
                <a className="inline-flex items-center gap-1 text-caption-bold font-caption-bold text-default-font underline underline-offset-2 transition-colors hover:text-brand-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring" href={searchHref}>
                  <Search className="h-3.5 w-3.5" />
                  Live search
                </a>
              </div>

              {correlationMatches.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {correlationMatches.slice(0, 5).map((entry) => {
              const humanId = getString(entry.human_id) || 'Timeline';
              const entityType = getString(entry.entity_type);
              const title = getString(entry.title);
              const status = getString(entry.status);
              const priority = getString(entry.priority);
              const updatedAt = getString(entry.updated_at);
              const href = getEntityHref(entityType, humanId);
              const icon = getEntityIcon(entityType);
              const state = getStateValue(entityType, status);
              const cardContent = (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    {icon}
                    <span className="text-caption-bold font-caption-bold text-default-font">{humanId}</span>
                    {state ? <State state={state} variant="small" /> : null}
                    {priority ? <Priority priority={priorityToUIPriority(priority as PriorityType)} size="mini" /> : null}
                  </div>
                  {title && <div className="mt-1 line-clamp-1 text-body font-body text-default-font">{title}</div>}
                  {updatedAt && <div className="mt-1 text-caption font-caption text-subtext-color">Updated {new Date(updatedAt).toLocaleString()}</div>}
                </>
              );

              return href ? (
                <Link
                  key={`${humanId}-${title || ''}`}
                  to={href}
                  className="rounded-md bg-neutral-200 px-2.5 py-2 transition-colors hover:bg-neutral-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
                >
                  {cardContent}
                </Link>
              ) : (
                <div key={`${humanId}-${title || ''}`} className="rounded-md bg-neutral-200 px-2.5 py-2">
                  {cardContent}
                </div>
              );
                  })}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </EnrichmentBlockSection>
  );
}
