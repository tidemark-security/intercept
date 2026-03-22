import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { MetricsService } from '@/types/generated/services/MetricsService';
import type { SOCMetricsResponse } from '@/types/generated/models/SOCMetricsResponse';
import type { AnalystMetricsResponse } from '@/types/generated/models/AnalystMetricsResponse';
import type { AlertMetricsResponse } from '@/types/generated/models/AlertMetricsResponse';
import type { AITriageMetricsResponse } from '@/types/generated/models/AITriageMetricsResponse';
import type { AIChatMetricsResponse } from '@/types/generated/models/AIChatMetricsResponse';
import type { Priority } from '@/types/generated/models/Priority';

/**
 * Shared options for all metrics hooks
 */
interface MetricsOptions {
  /** Period start (ISO8601 string). Defaults to 7 days ago. */
  start?: string;
  /** Period end (ISO8601 string). Defaults to now. */
  end?: string;
  /** Filter by priority level */
  priority?: Priority;
  /** Whether the query is enabled */
  enabled?: boolean;
}

interface SOCMetricsOptions extends MetricsOptions {
  /** Filter by alert source */
  source?: string;
}

interface AnalystMetricsOptions extends MetricsOptions {
  /** Filter by analyst username */
  analyst?: string;
}

interface AlertMetricsOptions extends MetricsOptions {
  /** Filter by alert source */
  source?: string;
  /** Dimension to group by: 'source', 'title', or 'tag' */
  groupBy?: 'source' | 'title' | 'tag';
}

interface AIMetricsOptions {
  /** Period start (ISO8601 string). Defaults to 7 days ago. */
  start?: string;
  /** Period end (ISO8601 string). Defaults to now. */
  end?: string;
  /** Whether the query is enabled */
  enabled?: boolean;
}

/**
 * Format Date to ISO8601 string with Z suffix for API
 */
function formatDateForApi(date: Date | string | undefined): string | undefined {
  if (!date) return undefined;
  if (typeof date === 'string') return date;
  return date.toISOString();
}

/**
 * Hook to fetch SOC-level summary metrics
 * 
 * Includes:
 * - MTTT (Mean Time to Triage) - p50, mean, p95
 * - MTTR (Mean Time to Resolution) - p50, mean, p95
 * - TP/FP/BP rates
 * - Alert, case, and task counts
 * - Time series breakdown by 15-minute windows
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useSOCMetrics({
 *   start: '2025-12-01T00:00:00Z',
 *   end: '2025-12-07T00:00:00Z',
 * });
 * ```
 */
export function useSOCMetrics(
  options: SOCMetricsOptions = {}
): UseQueryResult<SOCMetricsResponse, Error> {
  const { start, end, priority, source, enabled = true } = options;

  return useQuery({
    queryKey: ['metrics', 'soc', { start, end, priority, source }],
    queryFn: () =>
      MetricsService.getSocMetricsApiV1MetricsSocGet({
        start: formatDateForApi(start),
        end: formatDateForApi(end),
        priority: priority ?? null,
        source: source ?? null,
      }),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes - data refreshes every 15 min anyway
    refetchInterval: 5 * 60 * 1000, // Refetch every 5 minutes
  });
}

/**
 * Hook to fetch per-analyst performance metrics (Admin only)
 * 
 * Includes:
 * - Per-analyst triage volume
 * - TP/FP/escalation rates per analyst
 * - MTTT comparison to team median
 * - Cases and tasks completed
 * 
 * @example
 * ```tsx
 * const { data, isLoading, error } = useAnalystMetrics({
 *   start: '2025-12-01T00:00:00Z',
 * });
 * 
 * // Note: Returns 403 if user is not admin
 * ```
 */
export function useAnalystMetrics(
  options: AnalystMetricsOptions = {}
): UseQueryResult<AnalystMetricsResponse, Error> {
  const { start, end, analyst, enabled = true } = options;

  return useQuery({
    queryKey: ['metrics', 'analyst', { start, end, analyst }],
    queryFn: () =>
      MetricsService.getAnalystMetricsApiV1MetricsAnalystGet({
        start: formatDateForApi(start),
        end: formatDateForApi(end),
        analyst: analyst ?? null,
      }),
    enabled,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch alert performance metrics for detection engineering
 * 
 * Includes:
 * - Alert volume by source
 * - FP/escalation rates by source
 * - Hourly volume patterns
 * - Time series breakdown
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useAlertMetrics({
 *   source: 'crowdstrike',
 * });
 * ```
 */
export function useAlertMetrics(
  options: AlertMetricsOptions = {}
): UseQueryResult<AlertMetricsResponse, Error> {
  const { start, end, priority, source, groupBy = 'source', enabled = true } = options;

  return useQuery({
    queryKey: ['metrics', 'alert', { start, end, priority, source, groupBy }],
    queryFn: () =>
      MetricsService.getAlertMetricsApiV1MetricsAlertGet({
        start: formatDateForApi(start),
        end: formatDateForApi(end),
        priority: priority ?? null,
        source: source ?? null,
        groupBy: groupBy,
      }),
    enabled,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch AI triage accuracy metrics
 * 
 * Includes:
 * - Acceptance/rejection rates
 * - Rejection breakdown by category
 * - Confidence correlation with acceptance
 * - Weekly trending for tracking improvements
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useAITriageMetrics({
 *   start: '2025-12-01T00:00:00Z',
 *   end: '2025-12-31T00:00:00Z',
 * });
 * ```
 */
export function useAITriageMetrics(
  options: AIMetricsOptions = {}
): UseQueryResult<AITriageMetricsResponse, Error> {
  const { start, end, enabled = true } = options;

  return useQuery({
    queryKey: ['metrics', 'ai-triage', { start, end }],
    queryFn: () =>
      MetricsService.getAiTriageMetricsApiV1MetricsAiTriageGet({
        start: formatDateForApi(start),
        end: formatDateForApi(end),
      }),
    enabled,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch AI chat feedback metrics
 * 
 * Includes:
 * - Positive/negative feedback counts
 * - Satisfaction rate
 * - Feedback engagement rate
 * - Weekly trending for tracking improvements
 * 
 * @example
 * ```tsx
 * const { data, isLoading } = useAIChatMetrics({
 *   start: '2025-12-01T00:00:00Z',
 * });
 * ```
 */
export function useAIChatMetrics(
  options: AIMetricsOptions = {}
): UseQueryResult<AIChatMetricsResponse, Error> {
  const { start, end, enabled = true } = options;

  return useQuery({
    queryKey: ['metrics', 'ai-chat', { start, end }],
    queryFn: () =>
      MetricsService.getAiChatMetricsApiV1MetricsAiChatGet({
        start: formatDateForApi(start),
        end: formatDateForApi(end),
      }),
    enabled,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });
}

/**
 * Helper to calculate date range presets
 */
export function getDateRangePreset(preset: 'today' | '7d' | '30d' | '90d'): { start: string; end: string } {
  const now = new Date();
  const end = now.toISOString();
  
  let start: Date;
  switch (preset) {
    case 'today':
      start = new Date(now);
      start.setHours(0, 0, 0, 0);
      break;
    case '7d':
      start = new Date(now);
      start.setDate(start.getDate() - 7);
      break;
    case '30d':
      start = new Date(now);
      start.setDate(start.getDate() - 30);
      break;
    case '90d':
      start = new Date(now);
      start.setDate(start.getDate() - 90);
      break;
  }
  
  return { start: start.toISOString(), end };
}
