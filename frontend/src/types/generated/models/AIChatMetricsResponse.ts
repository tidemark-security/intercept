/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AIChatMetricsSummary } from './AIChatMetricsSummary';
import type { AIChatWeeklyTrend } from './AIChatWeeklyTrend';
/**
 * Full AI chat feedback metrics response.
 */
export type AIChatMetricsResponse = {
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
    summary: AIChatMetricsSummary;
    /**
     * Weekly feedback trend
     */
    weekly_trend?: Array<AIChatWeeklyTrend>;
};

