/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Per-analyst metrics for a single time window.
 */
export type AnalystMetricsWindow = {
    /**
     * Start of the 15-minute window (UTC)
     */
    time_window: string;
    /**
     * Analyst username
     */
    analyst: string;
    /**
     * Alerts triaged by analyst
     */
    alerts_triaged?: number;
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
     * Alerts escalated
     */
    alerts_escalated?: number;
    /**
     * Duplicates identified
     */
    alerts_duplicate?: number;
    /**
     * Analyst's median MTTT
     */
    mttt_p50_seconds?: (number | null);
    /**
     * Analyst's mean MTTT
     */
    mttt_mean_seconds?: (number | null);
    /**
     * Cases assigned to analyst
     */
    cases_assigned?: number;
    /**
     * Cases closed by analyst
     */
    cases_closed?: number;
    /**
     * Tasks assigned to analyst
     */
    tasks_assigned?: number;
    /**
     * Tasks completed by analyst
     */
    tasks_completed?: number;
};

