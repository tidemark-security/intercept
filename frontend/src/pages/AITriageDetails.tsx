"use client";

import React, { useMemo } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { AdminPageLayout } from '@/components/layout/AdminPageLayout';
import { Loader } from '@/components/feedback/Loader';
import { Badge } from '@/components/data-display/Badge';
import { Table } from '@/components/data-display/Table';
import { Button } from '@/components/buttons/Button';
import { Select } from '@/components/forms/Select';
import { DateRangePicker, DateRangeValue } from '@/components/forms/DateRangePicker';
import { CopyableTimestamp } from '@/components/data-display/CopyableTimestamp';
import { useTriageDrillDown } from '@/hooks/useAIDrillDown';
import { useSession } from '@/contexts/sessionContext';
import { useTheme } from '@/contexts/ThemeContext';
import { parseRelativeTime, formatForBackend } from '@/utils/dateFilters';
import { cn } from '@/utils/cn';
import { AlertCircle, Check, CheckCircle, ChevronLeft, ChevronRight, Clock3, Copy, HelpCircle, XCircle } from 'lucide-react';
import type { RejectionCategory, TriageDisposition, RecommendationStatus, TriageRecommendationDetail } from '@/types/generated';

// Friendly labels
const REJECTION_CATEGORY_LABELS: Record<string, string> = {
  INCORRECT_DISPOSITION: 'Incorrect Disposition',
  WRONG_SUGGESTED_STATUS: 'Wrong Status',
  WRONG_PRIORITY: 'Wrong Priority',
  MISSING_CONTEXT: 'Missing Context',
  INCOMPLETE_ANALYSIS: 'Incomplete Analysis',
  PREFER_MANUAL_REVIEW: 'Prefer Manual',
  FALSE_REASONING: 'False Reasoning',
  OTHER: 'Other',
};

const DISPOSITION_LABELS: Record<string, string> = {
  TRUE_POSITIVE: 'True Positive',
  FALSE_POSITIVE: 'False Positive',
  BENIGN_POSITIVE: 'Benign Positive',
  BENIGN: 'Benign',
  NEEDS_INVESTIGATION: 'Needs Investigation',
  DUPLICATE: 'Duplicate',
  UNKNOWN: 'Unknown',
  INCONCLUSIVE: 'Unknown',
};

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pending',
  ACCEPTED: 'Accepted',
  REJECTED: 'Rejected',
  QUEUED: 'Queued',
  FAILED: 'Failed',
  SUPERSEDED: 'Superseded',
};

function formatEnumLabel(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
}

function getDispositionLabel(disposition: string): string {
  return DISPOSITION_LABELS[disposition] || formatEnumLabel(disposition);
}

function getRejectionCategoryLabel(category: string): string {
  return REJECTION_CATEGORY_LABELS[category] || formatEnumLabel(category);
}

const DISPOSITION_BADGE_VARIANTS: Record<string, 'success' | 'error' | 'warning' | 'neutral'> = {
  TRUE_POSITIVE: 'success',
  FALSE_POSITIVE: 'error',
  BENIGN_POSITIVE: 'warning',
  BENIGN: 'warning',
  UNKNOWN: 'neutral',
};

function getDispositionBadgeVariant(disposition: string): 'success' | 'error' | 'warning' | 'neutral' {
  return DISPOSITION_BADGE_VARIANTS[disposition] ?? 'neutral';
}

const STATUS_BADGE_VARIANTS: Record<string, 'success' | 'error' | 'warning' | 'neutral'> = {
  ACCEPTED: 'success',
  REJECTED: 'error',
  PENDING: 'warning',
  QUEUED: 'neutral',
  FAILED: 'neutral',
  SUPERSEDED: 'neutral',
};

function getStatusBadgeVariant(status: string): 'success' | 'error' | 'warning' | 'neutral' {
  return STATUS_BADGE_VARIANTS[status] ?? 'neutral';
}

function normalizeDispositionFilter(value: string | null): TriageDisposition | null {
  if (!value) {
    return null;
  }

  if (value === 'INCONCLUSIVE') {
    return 'UNKNOWN';
  }

  if (value === 'BENIGN_POSITIVE') {
    return 'BENIGN';
  }

  return value as TriageDisposition;
}

const DEFAULT_TIMEFRAME = '-7d';
const PAGE_SIZE = 25;

export default function AITriageDetails() {
  const { user } = useSession();
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Check admin access
  const isAdmin = user?.role === 'ADMIN';
  
  // Parse URL params
  const dispositionFilter = normalizeDispositionFilter(searchParams.get('disposition'));
  const rejectionCategoryFilter = searchParams.get('rejection_category') as RejectionCategory | null;
  const statusFilter = searchParams.get('status') as RecommendationStatus | null;
  const timeframePreset = searchParams.get('timeframe') || DEFAULT_TIMEFRAME;
  const customStart = searchParams.get('start');
  const customEnd = searchParams.get('end');
  const page = parseInt(searchParams.get('page') || '1', 10);
  
  // Calculate date range
  const dateRange = useMemo<DateRangeValue | null>(() => {
    if (customStart && customEnd) {
      return { start: customStart, end: customEnd, preset: 'custom' };
    }
    const range = parseRelativeTime(timeframePreset);
    if (range) {
      return {
        start: formatForBackend(range.start),
        end: formatForBackend(range.end),
        preset: timeframePreset,
      };
    }
    // Fallback to last 7 days
    const fallback = parseRelativeTime(DEFAULT_TIMEFRAME)!;
    return {
      start: formatForBackend(fallback.start),
      end: formatForBackend(fallback.end),
      preset: DEFAULT_TIMEFRAME,
    };
  }, [timeframePreset, customStart, customEnd]);
  
  const offset = (page - 1) * PAGE_SIZE;
  
  // Fetch data
  const { data, isLoading, error } = useTriageDrillDown({
    start: dateRange?.start,
    end: dateRange?.end,
    disposition: dispositionFilter || undefined,
    rejection_category: rejectionCategoryFilter || undefined,
    status: statusFilter || undefined,
    limit: PAGE_SIZE,
    offset,
    enabled: isAdmin,
  });
  
  // Update URL params helper
  const updateParams = (updates: Record<string, string | null>) => {
    const params = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(updates)) {
      if (value === null) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    }
    setSearchParams(params, { replace: true });
  };
  
  const handleDateRangeChange = (range: DateRangeValue | null) => {
    if (!range) {
      updateParams({ timeframe: null, start: null, end: null, page: null });
    } else if (range.preset && range.preset !== 'custom') {
      updateParams({ timeframe: range.preset, start: null, end: null, page: null });
    } else {
      updateParams({ timeframe: null, start: range.start, end: range.end, page: null });
    }
  };
  
  const handleFilterChange = (key: string, value: string | null) => {
    updateParams({ [key]: value, page: null });
  };
  
  const totalPages = data ? Math.ceil((data.total ?? 0) / PAGE_SIZE) : 0;
  
  // Build page title
  let pageTitle = 'AI Triage Recommendations';
  if (rejectionCategoryFilter) {
    pageTitle = `Rejected: ${getRejectionCategoryLabel(rejectionCategoryFilter)}`;
  } else if (dispositionFilter) {
    pageTitle = `Disposition: ${getDispositionLabel(dispositionFilter)}`;
  } else if (statusFilter) {
    pageTitle = `Status: ${STATUS_LABELS[statusFilter] || statusFilter}`;
  }
  
  if (!isAdmin) {
    return (
      <DefaultPageLayout>
        <div className="flex h-full items-center justify-center">
          <div className="text-center">
            <h1 className="text-heading-2 font-heading-2 text-error-600 mb-4">Access Denied</h1>
            <p className="text-body text-subtext-color">
              This page is only accessible to administrators.
            </p>
          </div>
        </div>
      </DefaultPageLayout>
    );
  }

  return (
    <AdminPageLayout
      title={pageTitle}
      subtitle="Review AI triage recommendation outcomes"
      actionButton={(
        <DateRangePicker
          value={dateRange}
          onChange={handleDateRangeChange}
          presets={['-24h', '-7d', '-30d', '-90d']}
          size="medium"
        />
      )}
    >
      <div className="flex flex-col gap-6 w-full">
        
        {/* Filters */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-body text-subtext-color">Disposition:</span>
            <Select
              className="w-56"
              placeholder="All"
              value={dispositionFilter || '__all__'}
              onValueChange={(val) => handleFilterChange('disposition', val === '__all__' ? null : val)}
            >
              <Select.Item value="__all__">All Dispositions</Select.Item>
              <Select.Item value="TRUE_POSITIVE">
                <span className="flex items-center gap-2">
                  <Check className="h-4 w-4" />
                  True Positive
                </span>
              </Select.Item>
              <Select.Item value="FALSE_POSITIVE">
                <span className="flex items-center gap-2">
                  <XCircle className="h-4 w-4" />
                  False Positive
                </span>
              </Select.Item>
              <Select.Item value="BENIGN">
                <span className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4" />
                  Benign Positive
                </span>
              </Select.Item>
              <Select.Item value="NEEDS_INVESTIGATION">
                <span className="flex items-center gap-2">
                  <HelpCircle className="h-4 w-4" />
                  Needs Investigation
                </span>
              </Select.Item>
              <Select.Item value="DUPLICATE">
                <span className="flex items-center gap-2">
                  <Copy className="h-4 w-4" />
                  Duplicate
                </span>
              </Select.Item>
              <Select.Item value="UNKNOWN">
                <span className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" />
                  Unknown
                </span>
              </Select.Item>
            </Select>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-body text-subtext-color">Rejection Reason:</span>
            <Select
              className="w-64"
              placeholder="All"
              value={rejectionCategoryFilter || '__all__'}
              onValueChange={(val) => handleFilterChange('rejection_category', val === '__all__' ? null : val)}
            >
              <Select.Item value="__all__">All Categories</Select.Item>
              <Select.Item value="INCORRECT_DISPOSITION">Incorrect Disposition</Select.Item>
              <Select.Item value="WRONG_SUGGESTED_STATUS">Wrong Status</Select.Item>
              <Select.Item value="WRONG_PRIORITY">Wrong Priority</Select.Item>
              <Select.Item value="MISSING_CONTEXT">Missing Context</Select.Item>
              <Select.Item value="INCOMPLETE_ANALYSIS">Incomplete Analysis</Select.Item>
              <Select.Item value="PREFER_MANUAL_REVIEW">Prefer Manual</Select.Item>
              <Select.Item value="FALSE_REASONING">False Reasoning</Select.Item>
              <Select.Item value="OTHER">Other</Select.Item>
            </Select>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-body text-subtext-color">Status:</span>
            <Select
              className="w-52"
              placeholder="All"
              value={statusFilter || '__all__'}
              onValueChange={(val) => handleFilterChange('status', val === '__all__' ? null : val)}
            >
              <Select.Item value="__all__">All Statuses</Select.Item>
              <Select.Item value="PENDING">
                <span className="flex items-center gap-2">
                  <Clock3 className="h-4 w-4" />
                  Pending
                </span>
              </Select.Item>
              <Select.Item value="ACCEPTED">
                <span className="flex items-center gap-2">
                  <Check className="h-4 w-4" />
                  Accepted
                </span>
              </Select.Item>
              <Select.Item value="REJECTED">
                <span className="flex items-center gap-2">
                  <XCircle className="h-4 w-4" />
                  Rejected
                </span>
              </Select.Item>
              <Select.Item value="QUEUED">
                <span className="flex items-center gap-2">
                  <Clock3 className="h-4 w-4" />
                  Queued
                </span>
              </Select.Item>
              <Select.Item value="FAILED">
                <span className="flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" />
                  Failed
                </span>
              </Select.Item>
            </Select>
          </div>
          
          {(dispositionFilter || rejectionCategoryFilter || statusFilter) && (
            <Button
              variant="neutral-tertiary"
              size="small"
              onClick={() => updateParams({ disposition: null, rejection_category: null, status: null, page: null })}
            >
              Clear Filters
            </Button>
          )}
        </div>
        
        {/* Results */}
        {isLoading ? (
          <Loader />
        ) : error ? (
          <div className="text-error-600">Failed to load data. Please ensure you have admin access.</div>
        ) : !data || !data.items || data.items.length === 0 ? (
          <div className="text-subtext-color text-center py-12">
            No recommendations found matching the selected filters.
          </div>
        ) : (
          <>
            {/* Results summary */}
            <div className="text-body text-subtext-color">
              Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total ?? 0)} of {data.total ?? 0} recommendations
            </div>
            
            {/* Table */}
            <div className="rounded-lg border border-neutral-border bg-default-background">
              <Table
                header={
                  <Table.HeaderRow>
                    <Table.HeaderCell>Alert</Table.HeaderCell>
                    <Table.HeaderCell>Disposition</Table.HeaderCell>
                    <Table.HeaderCell>Confidence</Table.HeaderCell>
                    <Table.HeaderCell>Status</Table.HeaderCell>
                    <Table.HeaderCell>Rejection Reason</Table.HeaderCell>
                    <Table.HeaderCell>Reviewed By</Table.HeaderCell>
                    <Table.HeaderCell>Reviewed At</Table.HeaderCell>
                    <Table.HeaderCell>Created At</Table.HeaderCell>
                  </Table.HeaderRow>
                }
              >
                {(data.items ?? []).map((item: TriageRecommendationDetail) => (
                  <Table.Row key={item.id}>
                    <Table.Cell>
                      <div className="flex max-w-[16rem] flex-col">
                        <Link
                          to={`/alerts/${item.alert_human_id}`}
                          className={cn(
                            'text-body-bold font-body-bold hover:underline',
                            isDarkTheme ? 'text-brand-primary' : 'text-brand-900'
                          )}
                        >
                          {item.alert_human_id}
                        </Link>
                        <span className="text-caption text-subtext-color truncate max-w-[16rem]">
                          {item.alert_title}
                        </span>
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      {item.disposition && (
                        <Badge
                          variant={getDispositionBadgeVariant(item.disposition)}
                          className="w-full"
                        >
                          {getDispositionLabel(item.disposition)}
                        </Badge>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <span className="text-body">
                        {item.confidence !== undefined ? `${(item.confidence * 100).toFixed(0)}%` : '-'}
                      </span>
                    </Table.Cell>
                    <Table.Cell>
                      {item.status && (
                        <Badge
                          variant={getStatusBadgeVariant(item.status)}
                          className="w-full"
                        >
                          {STATUS_LABELS[item.status] || item.status}
                        </Badge>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {item.rejection_category ? (
                        <div className="flex flex-col">
                          <span className="text-body text-default-font">
                            {getRejectionCategoryLabel(item.rejection_category)}
                          </span>
                          {item.rejection_reason && (
                            <span className="text-caption text-subtext-color truncate max-w-xs">
                              {item.rejection_reason}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-subtext-color">-</span>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {item.reviewed_by ? (
                        <span className="text-body">{item.reviewed_by}</span>
                      ) : (
                        <span className="text-subtext-color">-</span>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {item.reviewed_at ? (
                        <CopyableTimestamp
                          value={item.reviewed_at}
                          showFull={false}
                          variant="default-right"
                        />
                      ) : (
                        <span className="text-subtext-color">-</span>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <CopyableTimestamp
                        value={item.created_at}
                        showFull={false}
                        variant="default-right"
                      />
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table>
            </div>
            
            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-4">
                <Button
                  variant="neutral-secondary"
                  size="small"
                  icon={<ChevronLeft />}
                  disabled={page <= 1}
                  onClick={() => updateParams({ page: String(page - 1) })}
                >
                  Previous
                </Button>
                <span className="text-body text-subtext-color">
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="neutral-secondary"
                  size="small"
                  icon={<ChevronRight />}
                  disabled={page >= totalPages}
                  onClick={() => updateParams({ page: String(page + 1) })}
                >
                  Next
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </AdminPageLayout>
  );
}
