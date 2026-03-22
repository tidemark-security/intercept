/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertMetricsByDimension } from './AlertMetricsByDimension';
import type { AlertMetricsBySource } from './AlertMetricsBySource';
import type { AlertMetricsHourly } from './AlertMetricsHourly';
import type { AlertMetricsWindow } from './AlertMetricsWindow';
/**
 * Full alert performance metrics response.
 */
export type AlertMetricsResponse = {
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
     * Dimension used for grouping: 'source', 'title', or 'tag'
     */
    group_by?: string;
    /**
     * Breakdown by source (deprecated, use by_dimension)
     */
    by_source?: Array<AlertMetricsBySource>;
    /**
     * Breakdown by selected dimension
     */
    by_dimension?: Array<AlertMetricsByDimension>;
    /**
     * Volume by hour of day
     */
    by_hour?: Array<AlertMetricsHourly>;
    /**
     * Full time series
     */
    time_series?: Array<AlertMetricsWindow>;
};

