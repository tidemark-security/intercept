/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AITriageByCategory } from './AITriageByCategory';
import type { AITriageByDisposition } from './AITriageByDisposition';
import type { AITriageConfidenceCorrelation } from './AITriageConfidenceCorrelation';
import type { AITriageMetricsSummary } from './AITriageMetricsSummary';
import type { AITriageWeeklyTrend } from './AITriageWeeklyTrend';
/**
 * Full AI triage accuracy metrics response.
 */
export type AITriageMetricsResponse = {
    /**
     * Query period start
     */
    start_time: string;
    /**
     * Query period end
     */
    end_time: string;
    /**
     * Aggregated summary for the period
     */
    summary: AITriageMetricsSummary;
    /**
     * Rejection breakdown by category
     */
    by_category?: Array<AITriageByCategory>;
    /**
     * Breakdown by disposition
     */
    by_disposition?: Array<AITriageByDisposition>;
    /**
     * Confidence correlation
     */
    by_confidence?: Array<AITriageConfidenceCorrelation>;
    /**
     * Weekly acceptance trend
     */
    weekly_trend?: Array<AITriageWeeklyTrend>;
};

