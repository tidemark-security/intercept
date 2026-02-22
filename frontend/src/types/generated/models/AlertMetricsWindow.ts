/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Alert performance metrics for a single time window.
 */
export type AlertMetricsWindow = {
    /**
     * Start of the 15-minute window (UTC)
     */
    time_window: string;
    /**
     * Alert source/rule
     */
    source?: (string | null);
    /**
     * Alert priority
     */
    priority?: (string | null);
    /**
     * Hour of day (0-23)
     */
    hour_of_day?: (number | null);
    /**
     * Day of week (0=Sunday)
     */
    day_of_week?: (number | null);
    /**
     * Total alerts
     */
    alert_count?: number;
    /**
     * Closed alerts
     */
    alerts_closed?: number;
    /**
     * True positives
     */
    alerts_tp?: number;
    /**
     * False positives
     */
    alerts_fp?: number;
    /**
     * Benign positives
     */
    alerts_bp?: number;
    /**
     * Escalated
     */
    alerts_escalated?: number;
    /**
     * Duplicates
     */
    alerts_duplicate?: number;
    /**
     * FP rate for this source
     */
    fp_rate?: (number | null);
    /**
     * Escalation rate
     */
    escalation_rate?: (number | null);
};

