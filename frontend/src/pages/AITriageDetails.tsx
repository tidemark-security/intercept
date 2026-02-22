"use client";

import React, { useMemo } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { Loader } from '@/components/feedback/Loader';
import { Badge } from '@/components/data-display/Badge';
import { Table } from '@/components/data-display/Table';
import { Button } from '@/components/buttons/Button';
import { Select } from '@/components/forms/Select';
import { DateRangePicker, DateRangeValue } from '@/components/forms/DateRangePicker';
import { useTriageDrillDown } from '@/hooks/useAIDrillDown';
import { useSession } from '@/contexts/sessionContext';
import { parseRelativeTime, formatForBackend } from '@/utils/dateFilters';
import { formatAbsoluteTime } from '@/utils/dateFormatters';
import { ArrowLeft, ExternalLink, ChevronLeft, ChevronRight, Bot } from 'lucide-react';
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
  NEEDS_INVESTIGATION: 'Needs Investigation',
  DUPLICATE: 'Duplicate',
  INCONCLUSIVE: 'Inconclusive',
};

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pending',
  ACCEPTED: 'Accepted',
  REJECTED: 'Rejected',
  QUEUED: 'Queued',
  FAILED: 'Failed',
  SUPERSEDED: 'Superseded',
};

function getDispositionBadgeVariant(disposition: string): 'success' | 'error' | 'warning' | 'neutral' {
  switch (disposition) {
    case 'TRUE_POSITIVE': return 'success';
    case 'FALSE_POSITIVE': return 'error';
    case 'BENIGN_POSITIVE': return 'warning';
    default: return 'neutral';
  }
}

function getStatusBadgeVariant(status: string): 'success' | 'error' | 'warning' | 'neutral' {
  switch (status) {
    case 'ACCEPTED': return 'success';
    case 'REJECTED': return 'error';
    case 'PENDING': return 'warning';
    default: return 'neutral';
  }
}

const DEFAULT_TIMEFRAME = '-7d';
const PAGE_SIZE = 25;

export default function AITriageDetails() {
  const { user } = useSession();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Check admin access
  const isAdmin = user?.role === 'ADMIN';
  
  // Parse URL params
  const dispositionFilter = searchParams.get('disposition') as TriageDisposition | null;
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
    pageTitle = `Rejected: ${REJECTION_CATEGORY_LABELS[rejectionCategoryFilter] || rejectionCategoryFilter}`;
  } else if (dispositionFilter) {
    pageTitle = `Disposition: ${DISPOSITION_LABELS[dispositionFilter] || dispositionFilter}`;
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
    <DefaultPageLayout withContainer>
      <div className="flex flex-col gap-6 p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="neutral-secondary"
              size="small"
              icon={<ArrowLeft />}
              onClick={() => navigate('/reports?tab=ai-triage')}
            >
              Back to Reports
            </Button>
            <div className="flex items-center gap-2">
              <Bot className="w-6 h-6 text-brand-primary" />
              <h1 className="text-heading-2 font-heading-2 text-default-font">{pageTitle}</h1>
            </div>
          </div>
          
          <DateRangePicker
            value={dateRange}
            onChange={handleDateRangeChange}
            presets={['-24h', '-7d', '-30d', '-90d']}
            size="small"
          />
        </div>
        
        {/* Filters */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-body text-subtext-color">Disposition:</span>
            <Select
              placeholder="All"
              value={dispositionFilter || '__all__'}
              onValueChange={(val) => handleFilterChange('disposition', val === '__all__' ? null : val)}
            >
              <Select.Item value="__all__">All Dispositions</Select.Item>
              <Select.Item value="TRUE_POSITIVE">True Positive</Select.Item>
              <Select.Item value="FALSE_POSITIVE">False Positive</Select.Item>
              <Select.Item value="BENIGN_POSITIVE">Benign Positive</Select.Item>
              <Select.Item value="NEEDS_INVESTIGATION">Needs Investigation</Select.Item>
              <Select.Item value="DUPLICATE">Duplicate</Select.Item>
              <Select.Item value="INCONCLUSIVE">Inconclusive</Select.Item>
            </Select>
          </div>
          
          <div className="flex items-center gap-2">
            <span className="text-body text-subtext-color">Rejection Reason:</span>
            <Select
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
              placeholder="All"
              value={statusFilter || '__all__'}
              onValueChange={(val) => handleFilterChange('status', val === '__all__' ? null : val)}
            >
              <Select.Item value="__all__">All Statuses</Select.Item>
              <Select.Item value="PENDING">Pending</Select.Item>
              <Select.Item value="ACCEPTED">Accepted</Select.Item>
              <Select.Item value="REJECTED">Rejected</Select.Item>
              <Select.Item value="QUEUED">Queued</Select.Item>
              <Select.Item value="FAILED">Failed</Select.Item>
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
                    <Table.HeaderCell>Created</Table.HeaderCell>
                    <Table.HeaderCell></Table.HeaderCell>
                  </Table.HeaderRow>
                }
              >
                {(data.items ?? []).map((item: TriageRecommendationDetail) => (
                  <Table.Row key={item.id}>
                    <Table.Cell>
                      <div className="flex flex-col">
                        <span className="text-body-bold font-body-bold text-default-font">
                          {item.alert_human_id}
                        </span>
                        <span className="text-caption text-subtext-color truncate max-w-xs">
                          {item.alert_title}
                        </span>
                      </div>
                    </Table.Cell>
                    <Table.Cell>
                      {item.disposition && (
                        <Badge variant={getDispositionBadgeVariant(item.disposition)}>
                          {DISPOSITION_LABELS[item.disposition] || item.disposition}
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
                        <Badge variant={getStatusBadgeVariant(item.status)}>
                          {STATUS_LABELS[item.status] || item.status}
                        </Badge>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {item.rejection_category ? (
                        <div className="flex flex-col">
                          <span className="text-body text-default-font">
                            {REJECTION_CATEGORY_LABELS[item.rejection_category] || item.rejection_category}
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
                        <div className="flex flex-col">
                          <span className="text-body">{item.reviewed_by}</span>
                          {item.reviewed_at && (
                            <span className="text-caption text-subtext-color">
                              {formatAbsoluteTime(item.reviewed_at, 'MMM d, yyyy h:mm a')}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-subtext-color">-</span>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <span className="text-caption text-subtext-color">
                        {formatAbsoluteTime(item.created_at, 'MMM d, yyyy h:mm a')}
                      </span>
                    </Table.Cell>
                    <Table.Cell>
                      <Link to={`/alerts/${item.alert_human_id}`}>
                        <Button
                          variant="neutral-tertiary"
                          size="small"
                          icon={<ExternalLink className="w-4 h-4" />}
                        >
                          View Alert
                        </Button>
                      </Link>
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
    </DefaultPageLayout>
  );
}
