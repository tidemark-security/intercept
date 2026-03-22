/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AIChatMetricsResponse } from '../models/AIChatMetricsResponse';
import type { AITriageMetricsResponse } from '../models/AITriageMetricsResponse';
import type { AlertMetricsResponse } from '../models/AlertMetricsResponse';
import type { AnalystMetricsResponse } from '../models/AnalystMetricsResponse';
import type { ChatFeedbackDrillDownResponse } from '../models/ChatFeedbackDrillDownResponse';
import type { MessageFeedback } from '../models/MessageFeedback';
import type { Priority } from '../models/Priority';
import type { RecommendationStatus } from '../models/RecommendationStatus';
import type { RejectionCategory } from '../models/RejectionCategory';
import type { SOCMetricsResponse } from '../models/SOCMetricsResponse';
import type { TriageDisposition } from '../models/TriageDisposition';
import type { TriageRecommendationDrillDownResponse } from '../models/TriageRecommendationDrillDownResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MetricsService {
    /**
     * Get SOC operational metrics
     * Query SOC operational metrics aggregated in 15-minute windows.
     *
     * **Metric Types:**
     * - `soc` - SOC-level summary: MTTT, MTTR, TP/FP/BP rates, case/alert/task counts
     * - `analyst` - Per-analyst performance: triage volume, outcome mix, timing comparison (ADMIN ONLY)
     * - `alert` - Alert performance: volume by source, hourly patterns, FP rates by rule
     *
     * **Time Range:**
     * - Start and end times are automatically binned to 15-minute boundaries
     * - Default range is last 7 days if not specified
     * - Format: ISO8601 with timezone (e.g., '2025-12-01T00:00:00Z')
     *
     * **Filters:**
     * - `priority` - Filter by priority level (INFO, LOW, MEDIUM, HIGH, CRITICAL, EXTREME)
     * - `source` - Filter by alert source (for soc and alert types)
     * - `analyst` - Filter by analyst username (for analyst type, admin only)
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getMetricsApiV1MetricsGet({
        type,
        start,
        end,
        priority,
        source,
        analyst,
        groupBy,
    }: {
        /**
         * Metric type: 'soc' for SOC summary, 'analyst' for per-analyst (admin only), 'alert' for detection engineering
         */
        type: 'soc' | 'analyst' | 'alert',
        /**
         * Period start (ISO8601 with 'Z' suffix, e.g., '2025-12-01T00:00:00Z'). Defaults to 7 days ago.
         */
        start?: (string | null),
        /**
         * Period end (ISO8601 with 'Z' suffix). Defaults to now.
         */
        end?: (string | null),
        /**
         * Filter by priority level
         */
        priority?: (Priority | null),
        /**
         * Filter by alert source (for type=soc or type=alert)
         */
        source?: (string | null),
        /**
         * Filter by analyst username (for type=analyst, admin only)
         */
        analyst?: (string | null),
        /**
         * Dimension to group by for type=alert: 'source', 'title', or 'tag'
         */
        groupBy?: (string | null),
    }): CancelablePromise<(SOCMetricsResponse | AnalystMetricsResponse | AlertMetricsResponse)> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics',
            query: {
                'type': type,
                'start': start,
                'end': end,
                'priority': priority,
                'source': source,
                'analyst': analyst,
                'group_by': groupBy,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get SOC summary metrics
     * Shorthand for GET /metrics?type=soc
     * @returns SOCMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getSocMetricsApiV1MetricsSocGet({
        start,
        end,
        priority,
        source,
    }: {
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
        /**
         * Filter by priority
         */
        priority?: (Priority | null),
        /**
         * Filter by alert source
         */
        source?: (string | null),
    }): CancelablePromise<SOCMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/soc',
            query: {
                'start': start,
                'end': end,
                'priority': priority,
                'source': source,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get analyst performance metrics (admin only)
     * Per-analyst performance metrics. Requires admin role.
     * @returns AnalystMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getAnalystMetricsApiV1MetricsAnalystGet({
        start,
        end,
        analyst,
    }: {
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
        /**
         * Filter by analyst username
         */
        analyst?: (string | null),
    }): CancelablePromise<AnalystMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/analyst',
            query: {
                'start': start,
                'end': end,
                'analyst': analyst,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get alert performance metrics
     * Alert performance metrics for detection engineering analysis.
     * @returns AlertMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getAlertMetricsApiV1MetricsAlertGet({
        start,
        end,
        source,
        priority,
        groupBy = 'source',
    }: {
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
        /**
         * Filter by alert source
         */
        source?: (string | null),
        /**
         * Filter by priority
         */
        priority?: (Priority | null),
        /**
         * Dimension to group by: 'source', 'title', or 'tag'
         */
        groupBy?: string,
    }): CancelablePromise<AlertMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/alert',
            query: {
                'start': start,
                'end': end,
                'source': source,
                'priority': priority,
                'group_by': groupBy,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get AI triage accuracy metrics
     * AI triage recommendation accuracy metrics for agent performance monitoring.
     *
     * Includes:
     * - Acceptance/rejection rates
     * - Rejection breakdown by category
     * - Disposition accuracy
     * - Confidence correlation with acceptance
     * - Weekly trending for tracking improvements
     * @returns AITriageMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getAiTriageMetricsApiV1MetricsAiTriageGet({
        start,
        end,
    }: {
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
    }): CancelablePromise<AITriageMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/ai-triage',
            query: {
                'start': start,
                'end': end,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get AI chat feedback metrics
     * AI chat assistant feedback metrics for agent performance monitoring.
     *
     * Includes:
     * - Positive/negative feedback counts
     * - Satisfaction rate
     * - Feedback engagement rate
     * - Weekly trending for tracking improvements
     * @returns AIChatMetricsResponse Successful Response
     * @throws ApiError
     */
    public static getAiChatMetricsApiV1MetricsAiChatGet({
        start,
        end,
    }: {
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
    }): CancelablePromise<AIChatMetricsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/ai-chat',
            query: {
                'start': start,
                'end': end,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get AI triage recommendations drill-down (admin only)
     * Drill-down endpoint for AI triage recommendations. Returns individual recommendations
     * with linked alert information for detailed analysis.
     *
     * **Admin Only**: This endpoint exposes detailed triage data across all users.
     *
     * **Filters:**
     * - `disposition` - Filter by recommended disposition
     * - `rejection_category` - Filter by rejection category
     * - `status` - Filter by recommendation status
     * - `start/end` - Time range for created_at
     *
     * **Pagination:**
     * - `limit` - Maximum items to return (default 50, max 200)
     * - `offset` - Number of items to skip
     * @returns TriageRecommendationDrillDownResponse Successful Response
     * @throws ApiError
     */
    public static getAiTriageRecommendationsDrilldownApiV1MetricsAiTriageRecommendationsGet({
        disposition,
        rejectionCategory,
        status,
        start,
        end,
        limit = 50,
        offset,
    }: {
        /**
         * Filter by disposition
         */
        disposition?: (TriageDisposition | null),
        /**
         * Filter by rejection category
         */
        rejectionCategory?: (RejectionCategory | null),
        /**
         * Filter by status
         */
        status?: (RecommendationStatus | null),
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
        /**
         * Maximum items to return
         */
        limit?: number,
        /**
         * Items to skip
         */
        offset?: number,
    }): CancelablePromise<TriageRecommendationDrillDownResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/ai-triage/recommendations',
            query: {
                'disposition': disposition,
                'rejection_category': rejectionCategory,
                'status': status,
                'start': start,
                'end': end,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get AI chat feedback messages drill-down (admin only)
     * Drill-down endpoint for AI chat messages with feedback. Returns individual messages
     * with session and user information for detailed analysis.
     *
     * **Admin Only**: This endpoint exposes message content across all users.
     *
     * **Filters:**
     * - `feedback` - Filter by feedback type (POSITIVE or NEGATIVE)
     * - `start/end` - Time range for created_at
     *
     * **Pagination:**
     * - `limit` - Maximum items to return (default 50, max 200)
     * - `offset` - Number of items to skip
     * @returns ChatFeedbackDrillDownResponse Successful Response
     * @throws ApiError
     */
    public static getAiChatFeedbackDrilldownApiV1MetricsAiChatFeedbackMessagesGet({
        feedback,
        start,
        end,
        limit = 50,
        offset,
    }: {
        /**
         * Filter by feedback type
         */
        feedback?: (MessageFeedback | null),
        /**
         * Period start (ISO8601)
         */
        start?: (string | null),
        /**
         * Period end (ISO8601)
         */
        end?: (string | null),
        /**
         * Maximum items to return
         */
        limit?: number,
        /**
         * Items to skip
         */
        offset?: number,
    }): CancelablePromise<ChatFeedbackDrillDownResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/metrics/ai-chat/feedback-messages',
            query: {
                'feedback': feedback,
                'start': start,
                'end': end,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
