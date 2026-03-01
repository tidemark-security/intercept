"use client";

import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { DefaultPageLayout } from '@/components/layout/DefaultPageLayout';
import { Loader } from '@/components/feedback/Loader';
import { Badge } from '@/components/data-display/Badge';
import { Table } from '@/components/data-display/Table';
import { SemiDonutChart } from '@/components/data-display/SemiDonutChart';
import { Button } from '@/components/buttons/Button';
import { ToggleGroup } from '@/components/buttons/ToggleGroup';

import { StatCard } from '@/components/cards/StatCard';
import { Select } from '@/components/forms/Select';
import { DateRangePicker, DateRangeValue } from '@/components/forms/DateRangePicker';
import { CopyableTimestamp } from '@/components/data-display/CopyableTimestamp';
import { useSOCMetrics, useAnalystMetrics, useAlertMetrics, useAITriageMetrics, useAIChatMetrics } from '@/hooks/useMetrics';
import { useChatFeedbackDrillDown } from '@/hooks/useAIDrillDown';
import { useSession } from '@/contexts/sessionContext';
import { useTheme } from '@/contexts/ThemeContext';
import { useReportsURLState, ReportTabType } from '@/hooks/useReportsURLState';
import { formatAbsoluteTime } from '@/utils/dateFormatters';
import { Activity, AlertTriangle, Bot, CheckCircle, ChevronLeft, ChevronRight, Clock, ExternalLink, MessageSquare, ThumbsDown, ThumbsUp, TrendingUp, Users } from 'lucide-react';
import type { ChatFeedbackMessageDetail, MessageFeedback } from '@/types/generated';
import { ScatterChart, Scatter } from 'recharts';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

type TabType = ReportTabType;
type AlertGroupBy = 'source' | 'title' | 'tag';

// Friendly labels for rejection categories
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

const CHART_COLORS_DARK = {
  tp: '#D0FF00', 
  fp: '#FF0055', 
  bp: '#2A1E5C', 
  escalated: '#00FFD9',
  alerts: '#FF0055',
  cases: '#00FFD9',
  tasks: '#2A1E5C', 
};

const CHART_COLORS_LIGHT = {
  tp: 'rgb(182, 230, 0)', 
  fp: '#D70047',
  bp: '#5332D0', 
  escalated: '#009181',
  alerts: '#D70047', 
  cases: '#5332D0', 
  tasks: '#262626',
};

const PIE_COLORS_DARK = ['#D0FF00', '#00E2C2', '#5F40EB', '#A3A3A3', '#FF0055'];
const PIE_COLORS_LIGHT = ['rgb(182, 230, 0)', '#5332D0', '#262626', '#009181', '#D70047'];
const CHART_ANIMATION_DURATION_MS = 300;
const CHAT_FEEDBACK_PAGE_SIZE = 25;

/**
 * Format seconds to human-readable duration
 */
function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '-';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

/**
 * Format percentage
 */
function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * Normalize chart label text to Title Case (e.g. UPPER_SNAKE_CASE -> Upper Snake Case)
 */
function formatChartLabel(value: string | null | undefined): string {
  if (!value) return 'Unknown';

  const normalized = value
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim()
    .toLowerCase();

  if (!normalized) return 'Unknown';

  return normalized.replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatChartLegendLabel(value: string | number | undefined | null): string {
  return formatChartLabel(value === undefined || value === null ? undefined : String(value));
}

function formatChartTooltipLabel(value: React.ReactNode, name?: string | number): [React.ReactNode, string] {
  return [value, formatChartLegendLabel(name)];
}

function normalizePercentValue(value: number | null | undefined): number {
  if (value === null || value === undefined || Number.isNaN(value)) return 0;
  const normalized = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, normalized));
}

function parseConfidenceBucketToPercent(bucket: string | null | undefined): number {
  if (!bucket) return 0;
  const trimmed = bucket.trim();

  const rangeMatch = trimmed.match(/^(\d*\.?\d+)\s*-\s*(\d*\.?\d+)$/);
  if (rangeMatch) {
    const minValue = Number(rangeMatch[1]);
    const maxValue = Number(rangeMatch[2]);
    if (!Number.isNaN(minValue) && !Number.isNaN(maxValue)) {
      return normalizePercentValue((minValue + maxValue) / 2);
    }
  }

  const numericValue = Number(trimmed);
  return normalizePercentValue(Number.isNaN(numericValue) ? 0 : numericValue);
}

function Reports() {
  const { user } = useSession();
  const { resolvedTheme } = useTheme();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'ADMIN';
  const isDarkTheme = resolvedTheme === 'dark';
  const CHART_COLORS = isDarkTheme ? CHART_COLORS_DARK : CHART_COLORS_LIGHT;
  const PIE_COLORS = isDarkTheme ? PIE_COLORS_DARK : PIE_COLORS_LIGHT;
  
  // URL-synced state for bookmarkable reports
  const { activeTab, setActiveTab, dateRange, setDateRange } = useReportsURLState();
  const [alertGroupBy, setAlertGroupBy] = useState<AlertGroupBy>('source');
  const [chatFeedbackFilter, setChatFeedbackFilter] = useState<MessageFeedback | '__all__'>('__all__');
  const [chatFeedbackPage, setChatFeedbackPage] = useState(1);
  
  // Extract start/end from dateRange, default to last 7 days if null
  const { start, end } = useMemo(() => {
    if (dateRange) {
      return { start: dateRange.start, end: dateRange.end };
    }
    // "All time" - use a very old start date
    return { 
      start: new Date(0).toISOString(), 
      end: new Date().toISOString() 
    };
  }, [dateRange]);
  
  // Fetch metrics based on active tab
  const { data: socData, isLoading: socLoading, error: socError } = useSOCMetrics({ 
    start, 
    end,
    enabled: activeTab === 'soc'
  });
  
  const { data: analystData, isLoading: analystLoading, error: analystError } = useAnalystMetrics({ 
    start, 
    end,
    enabled: activeTab === 'analyst' && isAdmin
  });
  
  const { data: alertData, isLoading: alertLoading, error: alertError } = useAlertMetrics({ 
    start, 
    end,
    groupBy: alertGroupBy,
    enabled: activeTab === 'alert'
  });

  const { data: aiTriageData, isLoading: aiTriageLoading, error: aiTriageError } = useAITriageMetrics({ 
    start, 
    end,
    enabled: activeTab === 'ai-triage'
  });

  const { data: aiChatData, isLoading: aiChatLoading, error: aiChatError } = useAIChatMetrics({ 
    start, 
    end,
    enabled: activeTab === 'ai-chat'
  });

  const chatFeedbackOffset = (chatFeedbackPage - 1) * CHAT_FEEDBACK_PAGE_SIZE;
  const chatFeedbackFilterValue = chatFeedbackFilter === '__all__' ? undefined : chatFeedbackFilter;

  const {
    data: chatFeedbackData,
    isLoading: chatFeedbackLoading,
    error: chatFeedbackError,
  } = useChatFeedbackDrillDown({
    start,
    end,
    feedback: chatFeedbackFilterValue,
    limit: CHAT_FEEDBACK_PAGE_SIZE,
    offset: chatFeedbackOffset,
    enabled: activeTab === 'ai-chat' && isAdmin,
  });

  useEffect(() => {
    setChatFeedbackPage(1);
  }, [chatFeedbackFilter, start, end]);

  // Prepare chart data for SOC overview
  const socChartData = useMemo(() => {
    if (!socData?.time_series) return [];
    
    // Aggregate by time window (reduce granularity for chart)
    const aggregated = new Map<string, { 
      time: string;
      alerts: number;
      cases: number;
      tasks: number;
      alertsClosed: number;
    }>();
    
    for (const window of socData.time_series) {
      const time = formatAbsoluteTime(window.time_window, 'MMM d h:mm a');
      const existing = aggregated.get(time) || { time, alerts: 0, cases: 0, tasks: 0, alertsClosed: 0 };
      existing.alerts += window.alert_count ?? 0;
      existing.cases += window.case_count ?? 0;
      existing.tasks += window.task_count ?? 0;
      existing.alertsClosed += window.alerts_closed ?? 0;
      aggregated.set(time, existing);
    }
    
    return Array.from(aggregated.values());
  }, [socData]);

  // Prepare disposition pie chart data
  const dispositionData = useMemo(() => {
    if (!socData?.summary) return [];
    const { total_alerts_tp, total_alerts_fp, total_alerts_bp } = socData.summary;
    return [
      { name: 'True Positive', value: total_alerts_tp ?? 0, color: CHART_COLORS.tp },
      { name: 'False Positive', value: total_alerts_fp ?? 0, color: CHART_COLORS.fp },
      { name: 'Benign Positive', value: total_alerts_bp ?? 0, color: CHART_COLORS.bp },
    ].filter(d => (d.value ?? 0) > 0);
  }, [CHART_COLORS, socData]);

  // Prepare hourly chart data
  const hourlyData = useMemo(() => {
    if (!alertData?.by_hour) return [];
    return alertData.by_hour.map(h => ({
      hour: `${h.hour_of_day}:00`,
      count: h.alert_count,
      avg: h.avg_alerts,
    }));
  }, [alertData]);

  const tabs = [
    { id: 'soc' as TabType, label: 'SOC Summary', icon: <Activity /> },
    { id: 'analyst' as TabType, label: 'Analyst Performance', icon: <Users />, adminOnly: true },
    { id: 'alert' as TabType, label: 'Alert Performance', icon: <AlertTriangle /> },
    { id: 'ai-triage' as TabType, label: 'AI Triage Accuracy', icon: <Bot /> },
    { id: 'ai-chat' as TabType, label: 'AI Chat Feedback', icon: <MessageSquare /> },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'soc':
        return renderSOCTab();
      case 'analyst':
        return renderAnalystTab();
      case 'alert':
        return renderAlertTab();
      case 'ai-triage':
        return renderAITriageTab();
      case 'ai-chat':
        return renderAIChatTab();
      default:
        return null;
    }
  };

  const renderSOCTab = () => {
    if (socLoading) return <Loader />;
    if (socError) return <div className="text-error-600">Failed to load SOC metrics</div>;
    if (!socData) return <div className="text-subtext-color">No data available</div>;

    const { summary } = socData;

    return (
      <div className="flex flex-col gap-8">
        {/* Key Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={<Clock />}
            label="Median Time to Triage"
            value={formatDuration(summary.mttt_p50_seconds)}
            subtext={`Mean: ${formatDuration(summary.mttt_mean_seconds)}`}
          />
          <StatCard
            icon={<CheckCircle />}
            label="Median Time to Resolution"
            value={formatDuration(summary.mttr_p50_seconds) ?? '-'}
            subtext={`Mean: ${formatDuration(summary.mttr_mean_seconds)}`}
          />
          <StatCard
            icon={<TrendingUp />}
            label="True Positive Rate"
            value={formatPercent(summary.tp_rate)}
            badge={summary.fp_rate !== null && summary.fp_rate !== undefined ? {
              text: `FP: ${formatPercent(summary.fp_rate)}`,
              variant: summary.fp_rate > 0.3 ? 'error' : 'neutral'
            } : undefined}
          />
          <StatCard
            icon={<AlertTriangle />}
            label="Open Cases"
            value={summary.open_cases ?? 0}
            subtext={`${summary.open_tasks ?? 0} open tasks`}
          />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Volume Over Time */}
          <div className="lg:col-span-2 rounded-lg border border-neutral-border bg-default-background p-6">
            <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Activity Over Time</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={socChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="time" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Tooltip formatter={formatChartTooltipLabel} />
                <Legend formatter={formatChartLegendLabel} />
                <Line type="monotone" dataKey="alerts" stroke={CHART_COLORS.alerts} name="Alerts" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
                <Line type="monotone" dataKey="cases" stroke={CHART_COLORS.cases} name="Cases" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
                <Line type="monotone" dataKey="alertsClosed" stroke={CHART_COLORS.tp} name="Closed" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Disposition Pie */}
          <div className="rounded-lg border border-neutral-border bg-default-background p-6">
            <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Alert Disposition</h3>
            {dispositionData.length > 0 ? (
              <SemiDonutChart
                data={dispositionData}
                centerLabel="Closed"
                centerValue={dispositionData.reduce((sum, item) => sum + item.value, 0)}
                height={300}
                animationDuration={CHART_ANIMATION_DURATION_MS}
              />
            ) : (
              <div className="flex items-center justify-center h-[300px] text-subtext-color">
                No closed alerts in period
              </div>
            )}
          </div>
        </div>

        {/* Summary Stats */}
        <div className="rounded-lg border border-neutral-border bg-default-background p-6">
          <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Period Summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-center">
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_alerts}</div>
              <div className="text-caption text-subtext-color">Total Alerts</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_alerts_closed}</div>
              <div className="text-caption text-subtext-color">Alerts Closed</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_cases}</div>
              <div className="text-caption text-subtext-color">Cases Created</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_cases_closed}</div>
              <div className="text-caption text-subtext-color">Cases Closed</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_tasks}</div>
              <div className="text-caption text-subtext-color">Tasks Created</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_tasks_completed}</div>
              <div className="text-caption text-subtext-color">Tasks Completed</div>
            </div>
          </div>
        </div>

        {/* Last Refreshed */}
        {socData.refreshed_at && (
          <div className="text-caption text-subtext-color text-right">
            Data last refreshed: {formatAbsoluteTime(socData.refreshed_at, 'MMM d, yyyy h:mm a')}
          </div>
        )}
      </div>
    );
  };

  const renderAnalystTab = () => {
    if (!isAdmin) {
      return (
        <div className="flex items-center justify-center py-12">
          <span className="text-body text-subtext-color">Admin access required to view analyst metrics</span>
        </div>
      );
    }
    
    if (analystLoading) return <Loader />;
    if (analystError) return <div className="text-error-600">Failed to load analyst metrics (admin access required)</div>;
    if (!analystData || !analystData.analysts || analystData.analysts.length === 0) {
      return <div className="text-subtext-color">No analyst data available for this period</div>;
    }

    return (
      <div className="flex flex-col gap-6">
        {/* Team MTTT Comparison */}
        <div className="rounded-lg border border-neutral-border bg-default-background p-6">
          <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Analyst Performance Comparison</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={(analystData.analysts ?? []).slice(0, 10)} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="analyst" width={100} tick={{ fontSize: 12 }} />
              <Tooltip formatter={formatChartTooltipLabel} />
              <Legend formatter={formatChartLegendLabel} />
              <Bar dataKey="total_alerts_triaged" fill={CHART_COLORS.alerts} name="Alerts Triaged" animationDuration={CHART_ANIMATION_DURATION_MS} />
              <Bar dataKey="total_cases_closed" fill={CHART_COLORS.cases} name="Cases Closed" animationDuration={CHART_ANIMATION_DURATION_MS} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Analyst Table */}
        <div className="rounded-lg border border-neutral-border bg-default-background text-default-font p-6">
          <h3 className="text-heading-3 font-heading-3 mb-4">Detailed Analyst Metrics</h3>
          <Table
            header={
              <Table.HeaderRow>
                <Table.HeaderCell>Analyst</Table.HeaderCell>
                <Table.HeaderCell>Alerts Triaged</Table.HeaderCell>
                <Table.HeaderCell>TP Rate</Table.HeaderCell>
                <Table.HeaderCell>FP Rate</Table.HeaderCell>
                <Table.HeaderCell>MTTT (p50)</Table.HeaderCell>
                <Table.HeaderCell>vs Team</Table.HeaderCell>
                <Table.HeaderCell>Cases Closed</Table.HeaderCell>
                <Table.HeaderCell>Tasks Done</Table.HeaderCell>
              </Table.HeaderRow>
            }
          >
            {(analystData.analysts ?? []).map((analyst) => {
              const mtttDiff = analyst.mttt_p50_seconds && analyst.team_mttt_p50_seconds
                ? ((analyst.mttt_p50_seconds - analyst.team_mttt_p50_seconds) / analyst.team_mttt_p50_seconds) * 100
                : null;
              
              return (
                <Table.Row key={analyst.analyst}>
                  <Table.Cell>
                    <span className="text-body-bold font-body-bold">{analyst.analyst}</span>
                  </Table.Cell>
                  <Table.Cell>{analyst.total_alerts_triaged}</Table.Cell>
                  <Table.Cell>
                    <Badge variant={analyst.tp_rate && analyst.tp_rate > 0.7 ? 'success' : 'neutral'}>
                      {formatPercent(analyst.tp_rate)}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell>
                    <Badge variant={analyst.fp_rate && analyst.fp_rate > 0.3 ? 'error' : 'neutral'}>
                      {formatPercent(analyst.fp_rate)}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell>{formatDuration(analyst.mttt_p50_seconds)}</Table.Cell>
                  <Table.Cell>
                    {mtttDiff !== null && (
                      <Badge variant={mtttDiff < 0 ? 'success' : mtttDiff > 20 ? 'error' : 'neutral'}>
                        {mtttDiff > 0 ? '+' : ''}{mtttDiff.toFixed(0)}%
                      </Badge>
                    )}
                  </Table.Cell>
                  <Table.Cell>{analyst.total_cases_closed}</Table.Cell>
                  <Table.Cell>{analyst.total_tasks_completed}</Table.Cell>
                </Table.Row>
              );
            })}
          </Table>
        </div>

        {analystData.refreshed_at && (
          <div className="text-caption text-subtext-color text-right">
            Data last refreshed: {formatAbsoluteTime(analystData.refreshed_at, 'MMM d, yyyy h:mm a')}
          </div>
        )}
      </div>
    );
  };

  const renderAlertTab = () => {
    if (alertLoading) return <Loader />;
    if (alertError) return <div className="text-error-600">Failed to load alert metrics</div>;
    if (!alertData) return <div className="text-subtext-color">No data available</div>;

    const dimensionLabel = alertGroupBy === 'source' ? 'Source' : alertGroupBy === 'title' ? 'Alert Title' : 'Tag';

    return (
      <div className="flex flex-col gap-6">
        {/* Hourly Distribution */}
        <div className="rounded-lg border border-neutral-border bg-default-background p-6">
          <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Alert Volume by Hour of Day</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip formatter={formatChartTooltipLabel} />
              <Bar dataKey="count" fill={CHART_COLORS.alerts} name="Total Alerts" animationDuration={CHART_ANIMATION_DURATION_MS} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* By Dimension Table with Pivot Selector */}
        <div className="rounded-lg border border-neutral-border bg-default-background text-default-font p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-heading-3 font-heading-3">Alert Performance by {dimensionLabel}</h3>
            <div className="flex items-center gap-2">
              <span className="text-sm text-subtext-color">Group by:</span>
              <ToggleGroup
                value={alertGroupBy}
                className="border rounded-md border-neutral-border"
                onValueChange={(value: string) => {
                  if (value) setAlertGroupBy(value as AlertGroupBy);
                }}
              >
                <ToggleGroup.Item icon={null} value="source" className="w-auto">
                  Source
                </ToggleGroup.Item>
                <ToggleGroup.Item icon={null} value="title" className="w-auto">
                  Title
                </ToggleGroup.Item>
                <ToggleGroup.Item icon={null} value="tag" className="w-auto">
                  Tag
                </ToggleGroup.Item>
              </ToggleGroup>
            </div>
          </div>
          {(alertData.by_dimension ?? []).length > 0 ? (
            <Table
              header={
                <Table.HeaderRow>
                  <Table.HeaderCell>{dimensionLabel}</Table.HeaderCell>
                  <Table.HeaderCell>Total Alerts</Table.HeaderCell>
                  <Table.HeaderCell>Closed</Table.HeaderCell>
                  <Table.HeaderCell>True Positive</Table.HeaderCell>
                  <Table.HeaderCell>False Positive</Table.HeaderCell>
                  <Table.HeaderCell>FP Rate</Table.HeaderCell>
                  <Table.HeaderCell>Escalated</Table.HeaderCell>
                  <Table.HeaderCell>Escalation Rate</Table.HeaderCell>
                </Table.HeaderRow>
              }
            >
              {(alertData.by_dimension ?? []).map((item, idx) => (
                <Table.Row key={`${item.value || 'unknown'}-${idx}`}>
                  <Table.Cell>
                    <span className="text-body-bold font-body-bold">{item.value || 'Unknown'}</span>
                  </Table.Cell>
                  <Table.Cell>{item.total_alerts}</Table.Cell>
                  <Table.Cell>{item.total_closed}</Table.Cell>
                  <Table.Cell>
                    {item.total_tp}
                  </Table.Cell>
                  <Table.Cell>
                    {item.total_fp}
                  </Table.Cell>
                  <Table.Cell>
                    <Badge variant={item.fp_rate && item.fp_rate > 0.3 ? 'error' : item.fp_rate && item.fp_rate > 0.15 ? 'warning' : 'success'}>
                      {formatPercent(item.fp_rate)}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell>{item.total_escalated}</Table.Cell>
                  <Table.Cell>
                    <Badge variant="neutral">
                      {formatPercent(item.escalation_rate)}
                    </Badge>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table>
          ) : (
            <div className="text-subtext-color py-4">No {dimensionLabel.toLowerCase()} data available</div>
          )}
        </div>

        {alertData.refreshed_at && (
          <div className="text-caption text-subtext-color text-right">
            Data last refreshed: {formatAbsoluteTime(alertData.refreshed_at, 'MMM d, yyyy h:mm a')}
          </div>
        )}
      </div>
    );
  };

  const renderAITriageTab = () => {
    if (aiTriageLoading) return <Loader />;
    if (aiTriageError) return <div className="text-error-600">Failed to load AI triage metrics</div>;
    if (!aiTriageData) return <div className="text-subtext-color">No data available</div>;

    const { summary, by_category, by_disposition, by_confidence, weekly_trend } = aiTriageData;

    // Prepare category pie chart data
    const categoryData = (by_category ?? []).map((item, idx) => ({
      name: item.category ? (REJECTION_CATEGORY_LABELS[item.category] || formatChartLabel(item.category)) : 'Uncategorized',
      rawCategory: item.category,
      value: item.count ?? 0,
      color: PIE_COLORS[idx % PIE_COLORS.length],
    })).filter(d => d.value > 0);

    // Prepare disposition bar chart data
    const dispositionChartData = (by_disposition ?? []).map(item => ({
      disposition: formatChartLabel(item.disposition),
      rawDisposition: item.disposition,
      accepted: item.accepted ?? 0,
      rejected: item.rejected ?? 0,
      total: item.total ?? 0,
    }));

    // Navigate to drill-down pages (admin only)
    const handleCategoryClick = (category: string | null) => {
      if (!isAdmin || !category) return;
      const params = new URLSearchParams();
      params.set('rejection_category', category);
      params.set('status', 'REJECTED');
      if (dateRange?.preset && dateRange.preset !== 'custom') {
        params.set('timeframe', dateRange.preset);
      } else if (dateRange?.start && dateRange?.end) {
        params.set('start', dateRange.start);
        params.set('end', dateRange.end);
      }
      navigate(`/reports/ai-triage/details?${params.toString()}`);
    };

    const handleDispositionClick = (disposition: string | null) => {
      if (!isAdmin || !disposition) return;
      const params = new URLSearchParams();
      params.set('disposition', disposition);
      if (dateRange?.preset && dateRange.preset !== 'custom') {
        params.set('timeframe', dateRange.preset);
      } else if (dateRange?.start && dateRange?.end) {
        params.set('start', dateRange.start);
        params.set('end', dateRange.end);
      }
      navigate(`/reports/ai-triage/details?${params.toString()}`);
    };

    const handleViewAllRecommendations = () => {
      if (!isAdmin) return;
      const params = new URLSearchParams();
      if (dateRange?.preset && dateRange.preset !== 'custom') {
        params.set('timeframe', dateRange.preset);
      } else if (dateRange?.start && dateRange?.end) {
        params.set('start', dateRange.start);
        params.set('end', dateRange.end);
      }
      navigate(`/reports/ai-triage/details?${params.toString()}`);
    };

    // Prepare weekly trend line chart data
    const weeklyChartData = (weekly_trend ?? []).map(item => ({
      week: formatAbsoluteTime(item.week_start, 'MMM d'),
      total: item.total_recommendations ?? 0,
      accepted: item.accepted ?? 0,
      rejected: item.rejected ?? 0,
      rate: (item.acceptance_rate ?? 0) * 100,
    }));

    // Prepare confidence scatter data
    const confidenceData = (by_confidence ?? []).map(item => ({
      confidence: parseConfidenceBucketToPercent(item.confidence_bucket),
      acceptanceRate: normalizePercentValue(item.acceptance_rate ?? 0),
      total: item.total ?? 0,
    }));

    return (
      <div className="flex flex-col gap-8">
        {/* Key Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={<CheckCircle />}
            label="Acceptance Rate"
            value={formatPercent(summary.acceptance_rate)}
            badge={{
              text: `${summary.total_accepted ?? 0} accepted`,
              variant: 'success'
            }}
          />
          <StatCard
            icon={<AlertTriangle />}
            label="Rejection Rate"
            value={formatPercent(summary.rejection_rate)}
            badge={{
              text: `${summary.total_rejected ?? 0} rejected`,
              variant: (summary.rejection_rate ?? 0) > 0.3 ? 'error' : 'neutral'
            }}
          />
          <StatCard
            icon={<Bot />}
            label="Total Recommendations"
            value={summary.total_recommendations ?? 0}
            subtext={`${summary.total_pending ?? 0} pending review`}
          />
          <StatCard
            icon={<TrendingUp />}
            label="Avg Confidence"
            value={formatPercent(summary.avg_confidence)}
            subtext="AI confidence score"
          />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Weekly Trend */}
          <div className="rounded-lg border border-neutral-border bg-default-background p-6">
            <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Weekly Acceptance Trend</h3>
            {weeklyChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={weeklyChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
                  <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 12 }} unit="%" />
                  <Tooltip formatter={formatChartTooltipLabel} />
                  <Legend formatter={formatChartLegendLabel} />
                  <Line yAxisId="left" type="monotone" dataKey="accepted" stroke={CHART_COLORS.tp} name="Accepted" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
                  <Line yAxisId="left" type="monotone" dataKey="rejected" stroke={CHART_COLORS.fp} name="Rejected" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
                  <Line yAxisId="right" type="monotone" dataKey="rate" stroke={CHART_COLORS.alerts} name="Rate %" strokeWidth={2} strokeDasharray="5 5" animationDuration={CHART_ANIMATION_DURATION_MS} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[300px] text-subtext-color">
                No trend data available
              </div>
            )}
          </div>

          {/* Rejection Category Pie */}
          <div className="rounded-lg border border-neutral-border bg-default-background p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-heading-3 font-heading-3 text-default-font">Rejection Reasons</h3>
              {isAdmin && categoryData.length > 0 && (
                <button
                  onClick={() => {
                    const params = new URLSearchParams();
                    params.set('status', 'REJECTED');
                    if (dateRange?.preset && dateRange.preset !== 'custom') {
                      params.set('timeframe', dateRange.preset);
                    } else if (dateRange?.start && dateRange?.end) {
                      params.set('start', dateRange.start);
                      params.set('end', dateRange.end);
                    }
                    navigate(`/reports/ai-triage/details?${params.toString()}`);
                  }}
                  className={`flex items-center gap-1 text-sm hover:underline ${isDarkTheme ? 'text-brand-primary' : 'text-default-font'}`}
                >
                  View All <ExternalLink className="w-3 h-3" />
                </button>
              )}
            </div>
            {categoryData.length > 0 ? (
              <SemiDonutChart
                data={categoryData}
                centerLabel="Rejections"
                centerValue={categoryData.reduce((sum, item) => sum + item.value, 0)}
                height={300}
                animationDuration={CHART_ANIMATION_DURATION_MS}
                onSliceClick={isAdmin ? (item) => handleCategoryClick(item.rawCategory ?? null) : undefined}
              />
            ) : (
              <div className="flex items-center justify-center h-[300px] text-subtext-color">
                No rejections in period
              </div>
            )}
          </div>
        </div>

        {/* Bottom Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* By Disposition */}
          <div className="rounded-lg border border-neutral-border bg-default-background p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-heading-3 font-heading-3 text-default-font">Accuracy by Disposition</h3>
              {isAdmin && dispositionChartData.length > 0 && (
                <button
                  onClick={handleViewAllRecommendations}
                  className={`flex items-center gap-1 text-sm hover:underline ${isDarkTheme ? 'text-brand-primary' : 'text-default-font'}`}
                >
                  View All <ExternalLink className="w-3 h-3" />
                </button>
              )}
            </div>
            {dispositionChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <BarChart 
                  data={dispositionChartData} 
                  layout="vertical"
                  onClick={(data) => {
                    const payload = (data as { activePayload?: Array<{ payload?: { rawDisposition?: string } }> })?.activePayload;
                    if (payload?.[0]?.payload?.rawDisposition) {
                      handleDispositionClick(payload[0].payload.rawDisposition);
                    }
                  }}
                  style={{ cursor: isAdmin ? 'pointer' : 'default' }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="disposition" width={100} tick={{ fontSize: 12 }} />
                  <Tooltip formatter={formatChartTooltipLabel} />
                  <Legend formatter={formatChartLegendLabel} />
                  <Bar dataKey="accepted" stackId="a" fill={CHART_COLORS.tp} name="Accepted" animationDuration={CHART_ANIMATION_DURATION_MS} />
                  <Bar dataKey="rejected" stackId="a" fill={CHART_COLORS.fp} name="Rejected" animationDuration={CHART_ANIMATION_DURATION_MS} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[250px] text-subtext-color">
                No disposition data available
              </div>
            )}
          </div>

          {/* Confidence Correlation */}
          <div className="rounded-lg border border-neutral-border bg-default-background p-6">
            <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Confidence vs Acceptance Rate</h3>
            {confidenceData.length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <ScatterChart margin={{ top: 5, right: 10, left: 28, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="confidence"
                    name="Confidence"
                    domain={[0, 100]}
                    unit="%"
                    tick={{ fontSize: 12 }}
                    label={{ value: 'Confidence (%)', position: 'insideBottom', offset: -8 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="acceptanceRate"
                    name="Acceptance"
                    domain={[0, 100]}
                    unit="%"
                    tick={{ fontSize: 12 }}
                    width={56}
                    label={{ value: 'Acceptance Rate (%)', angle: -90, position: 'insideBottomLeft', dy: -10 }}
                  />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    formatter={(value, name) => [`${Number(value ?? 0).toFixed(1)}%`, formatChartLegendLabel(name)]}
                  />
                  <Scatter name="Buckets" data={confidenceData} fill={CHART_COLORS.alerts} animationDuration={CHART_ANIMATION_DURATION_MS}>
                    {confidenceData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={CHART_COLORS.alerts} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-[250px] text-subtext-color">
                No confidence data available
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderAIChatTab = () => {
    if (aiChatLoading) return <Loader />;
    if (aiChatError) return <div className="text-error-600">Failed to load AI chat metrics</div>;
    if (!aiChatData) return <div className="text-subtext-color">No data available</div>;

    const { summary, weekly_trend } = aiChatData;

    // Prepare weekly trend data
    const weeklyChartData = (weekly_trend ?? []).map(item => ({
      week: formatAbsoluteTime(item.week_start, 'MMM d'),
      positive: item.positive_feedback ?? 0,
      negative: item.negative_feedback ?? 0,
      satisfactionRate: (item.satisfaction_rate ?? 0) * 100,
    }));

    const totalFeedbackPages = chatFeedbackData ? Math.ceil((chatFeedbackData.total ?? 0) / CHAT_FEEDBACK_PAGE_SIZE) : 0;

    return (
      <div className="flex flex-col gap-8">
        {/* Key Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={<TrendingUp />}
            label="Satisfaction Rate"
            value={formatPercent(summary.satisfaction_rate)}
            badge={{
              text: (summary.satisfaction_rate ?? 0) >= 0.8 ? 'Great!' : (summary.satisfaction_rate ?? 0) >= 0.6 ? 'Good' : 'Needs Improvement',
              variant: (summary.satisfaction_rate ?? 0) >= 0.8 ? 'success' : (summary.satisfaction_rate ?? 0) >= 0.6 ? 'neutral' : 'warning'
            }}
          />
          <StatCard
            icon={<CheckCircle />}
            label="Positive Feedback"
            value={summary.positive_feedback ?? 0}
            subtext="Thumbs up"
          />
          <StatCard
            icon={<AlertTriangle />}
            label="Negative Feedback"
            value={summary.negative_feedback ?? 0}
            subtext="Thumbs down"
          />
          <StatCard
            icon={<MessageSquare />}
            label="Feedback Rate"
            value={formatPercent(summary.feedback_rate)}
            subtext={`${summary.total_with_feedback ?? 0} of ${summary.total_messages ?? 0} messages`}
          />
        </div>

        {/* Weekly Trend Chart */}
        <div className="rounded-lg border border-neutral-border bg-default-background p-6">
          <h3 className="text-heading-3 font-heading-3 text-default-font mb-4">Weekly Feedback Trend</h3>
          {weeklyChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={weeklyChartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week" tick={{ fontSize: 12 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 12 }} />
                <YAxis yAxisId="right" orientation="right" domain={[0, 100]} tick={{ fontSize: 12 }} unit="%" />
                <Tooltip formatter={formatChartTooltipLabel} />
                <Legend formatter={formatChartLegendLabel} />
                <Line yAxisId="left" type="monotone" dataKey="positive" stroke={CHART_COLORS.tp} name="Positive" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
                <Line yAxisId="left" type="monotone" dataKey="negative" stroke={CHART_COLORS.fp} name="Negative" strokeWidth={2} animationDuration={CHART_ANIMATION_DURATION_MS} />
                <Line yAxisId="right" type="monotone" dataKey="satisfactionRate" stroke={CHART_COLORS.alerts} name="Satisfaction %" strokeWidth={2} strokeDasharray="5 5" animationDuration={CHART_ANIMATION_DURATION_MS} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-[350px] text-subtext-color">
              No trend data available
            </div>
          )}
        </div>

        {/* Feedback Summary */}
        <div className="rounded-lg border border-neutral-border bg-default-background p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-heading-3 font-heading-3 text-default-font">Period Summary</h3>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_messages ?? 0}</div>
              <div className="text-caption text-subtext-color">Total AI Messages</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2 text-default-font">{summary.total_with_feedback ?? 0}</div>
              <div className="text-caption text-subtext-color">Messages w/ Feedback</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2">{summary.positive_feedback ?? 0}</div>
              <div className="text-caption text-subtext-color">Positive</div>
            </div>
            <div>
              <div className="text-heading-2 font-heading-2">{summary.negative_feedback ?? 0}</div>
              <div className="text-caption text-subtext-color">Negative</div>
            </div>
          </div>
        </div>

        {/* Feedback Details */}
        {isAdmin && (
          <div className="rounded-lg border border-neutral-border bg-default-background p-6">
            <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
              <h3 className="text-heading-3 font-heading-3 text-default-font">Feedback Messages</h3>
              <div className="flex items-center gap-2">
                <span className="text-body text-subtext-color">Feedback:</span>
                <Select
                  placeholder="All"
                  value={chatFeedbackFilter}
                  onValueChange={(val) => setChatFeedbackFilter(val as MessageFeedback | '__all__')}
                >
                  <Select.Item value="__all__">All Feedback</Select.Item>
                  <Select.Item value="POSITIVE">Positive</Select.Item>
                  <Select.Item value="NEGATIVE">Negative</Select.Item>
                </Select>
              </div>
            </div>

            {chatFeedbackLoading ? (
              <Loader />
            ) : chatFeedbackError ? (
              <div className="text-error-600">Failed to load feedback messages.</div>
            ) : !chatFeedbackData || !chatFeedbackData.items || chatFeedbackData.items.length === 0 ? (
              <div className="text-subtext-color text-center py-12">No messages found matching the selected filters.</div>
            ) : (
              <>
                <div className="text-body text-subtext-color mb-4">
                  Showing {chatFeedbackOffset + 1}–{Math.min(chatFeedbackOffset + CHAT_FEEDBACK_PAGE_SIZE, chatFeedbackData.total ?? 0)} of {chatFeedbackData.total ?? 0} messages
                </div>

                <div className="rounded-lg border border-neutral-border bg-default-background">
                  <Table
                    header={
                      <Table.HeaderRow>
                        <Table.HeaderCell>Feedback</Table.HeaderCell>
                        <Table.HeaderCell>User</Table.HeaderCell>
                        <Table.HeaderCell>Session</Table.HeaderCell>
                        <Table.HeaderCell>Message Preview</Table.HeaderCell>
                        <Table.HeaderCell>Time</Table.HeaderCell>
                        <Table.HeaderCell></Table.HeaderCell>
                      </Table.HeaderRow>
                    }
                  >
                    {(chatFeedbackData.items ?? []).map((item: ChatFeedbackMessageDetail) => (
                      <Table.Row key={item.id}>
                        <Table.Cell>
                          {item.feedback === 'POSITIVE' ? (
                            <Badge variant="success" className="w-full" icon={<ThumbsUp className="w-3 h-3" />}>
                              Positive
                            </Badge>
                          ) : (
                            <Badge variant="error" className="w-full" icon={<ThumbsDown className="w-3 h-3" />}>
                              Negative
                            </Badge>
                          )}
                        </Table.Cell>
                        <Table.Cell>
                          <div className="flex max-w-[14rem] flex-col">
                            <span className="text-body-bold font-body-bold text-default-font truncate max-w-[14rem]">
                              {item.display_name || item.username}
                            </span>
                            {item.display_name && (
                              <span className="text-caption text-subtext-color truncate max-w-[14rem]">
                                @{item.username}
                              </span>
                            )}
                          </div>
                        </Table.Cell>
                        <Table.Cell>
                          <div className="flex max-w-[16rem] flex-col">
                            <span className="text-body text-default-font truncate max-w-[16rem]">
                              {item.session_title || 'Untitled Session'}
                            </span>
                            <span className="text-caption text-subtext-color truncate max-w-[16rem]">
                              {item.flow_id}
                            </span>
                          </div>
                        </Table.Cell>
                        <Table.Cell>
                          <div className="max-w-md">
                            <p className="text-body text-default-font line-clamp-2">
                              {item.content}
                            </p>
                          </div>
                        </Table.Cell>
                        <Table.Cell>
                          <CopyableTimestamp
                            value={item.created_at}
                            showFull={false}
                            variant="default-right"
                          />
                        </Table.Cell>
                        <Table.Cell>
                          <Button
                            variant="neutral-tertiary"
                            size="small"
                            icon={<ExternalLink className="w-4 h-4" />}
                            onClick={() => navigate(`/ai-chat?session=${item.session_id}`)}
                          >
                            Open Chat
                          </Button>
                        </Table.Cell>
                      </Table.Row>
                    ))}
                  </Table>
                </div>

                {totalFeedbackPages > 1 && (
                  <div className="flex items-center justify-center gap-4 mt-4">
                    <Button
                      variant="neutral-secondary"
                      size="small"
                      icon={<ChevronLeft />}
                      disabled={chatFeedbackPage <= 1}
                      onClick={() => setChatFeedbackPage((prev) => Math.max(1, prev - 1))}
                    >
                      Previous
                    </Button>
                    <span className="text-body text-subtext-color">
                      Page {chatFeedbackPage} of {totalFeedbackPages}
                    </span>
                    <Button
                      variant="neutral-secondary"
                      size="small"
                      icon={<ChevronRight />}
                      disabled={chatFeedbackPage >= totalFeedbackPages}
                      onClick={() => setChatFeedbackPage((prev) => Math.min(totalFeedbackPages, prev + 1))}
                    >
                      Next
                    </Button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <DefaultPageLayout withContainer>
      <div className="container max-w-none flex h-full w-full flex-col items-start gap-6 py-8">
        {/* Header */}
        <div className="flex w-full items-center justify-between">
          <div className="flex flex-col gap-1">
            <span className="text-heading-1 font-heading-1 text-default-font">Reports</span>
            <span className="text-body text-subtext-color">SOC operational metrics and performance analysis</span>
          </div>
          
          {/* Date Range Selector */}
          <DateRangePicker
            value={dateRange}
            onChange={setDateRange}
            presets={['-24h', '-7d', '-30d', '-90d']}
            showAllTime={true}
            size="medium"
            variant="neutral-secondary"
          />
        </div>

        {/* Tab Navigation */}
        <div className="flex w-full border-b border-neutral-border">
          {tabs.map((tab) => {
            if (tab.adminOnly && !isAdmin) return null;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.id
                    ? `border-brand-primary ${isDarkTheme ? 'text-brand-primary' : 'text-brand-700'}`
                    : 'border-transparent text-subtext-color hover:text-default-font hover:border-neutral-300'
                }`}
              >
                {tab.icon}
                {tab.label}
                {tab.adminOnly && (
                  <Badge variant="neutral" className="text-xs">Admin</Badge>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab Content */}
        <div className="w-full">
          {renderTabContent()}
        </div>
      </div>
    </DefaultPageLayout>
  );
}

export default Reports;
