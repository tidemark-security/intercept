/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SOCMetricsSummary } from './SOCMetricsSummary';
import type { SOCMetricsWindow } from './SOCMetricsWindow';
/**
 * Full SOC metrics response with time series and summary.
 */
export type SOCMetricsResponse = {
    /**
     * Query period start (binned to 15-min)
     */
    start_time: string;
    /**
     * Query period end (binned to 15-min)
     */
    end_time: string;
    /**
     * Last materialized view refresh
     */
    refreshed_at?: (string | null);
    /**
     * Aggregated summary for the period
     */
    summary: SOCMetricsSummary;
    /**
     * Per-window breakdown
     */
    time_series?: Array<SOCMetricsWindow>;
};

