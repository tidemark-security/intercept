/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalystMetricsSummary } from './AnalystMetricsSummary';
import type { AnalystMetricsWindow } from './AnalystMetricsWindow';
/**
 * Full analyst metrics response.
 */
export type AnalystMetricsResponse = {
    /**
     * Query period start
     */
    start_time: string;
    /**
     * Query period end
     */
    end_time: string;
    /**
     * Last refresh timestamp
     */
    refreshed_at?: (string | null);
    /**
     * Per-analyst summaries
     */
    analysts?: Array<AnalystMetricsSummary>;
    /**
     * Time series by analyst
     */
    time_series?: Array<AnalystMetricsWindow>;
};

