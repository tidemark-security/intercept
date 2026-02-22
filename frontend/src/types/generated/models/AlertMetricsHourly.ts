/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Alert volume by hour of day.
 */
export type AlertMetricsHourly = {
    /**
     * Hour (0-23)
     */
    hour_of_day: number;
    /**
     * Total alerts
     */
    alert_count?: number;
    /**
     * Average alerts per day
     */
    avg_alerts?: number;
};

