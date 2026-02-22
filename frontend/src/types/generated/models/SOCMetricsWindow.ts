/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * SOC-level metrics for a single time window.
 */
export type SOCMetricsWindow = {
    /**
     * Start of the 15-minute window (UTC)
     */
    time_window: string;
    /**
     * Priority level filter
     */
    priority?: (string | null);
    /**
     * Alert source filter
     */
    alert_source?: (string | null);
    /**
     * Total alerts created
     */
    alert_count?: number;
    /**
     * Alerts closed (any disposition)
     */
    alerts_closed?: number;
    /**
     * Alerts closed as true positive
     */
    alerts_tp?: number;
    /**
     * Alerts closed as false positive
     */
    alerts_fp?: number;
    /**
     * Alerts closed as benign positive
     */
    alerts_bp?: number;
    /**
     * Alerts closed as duplicate
     */
    alerts_duplicate?: number;
    /**
     * Alerts closed unresolved
     */
    alerts_unresolved?: number;
    /**
     * Alerts escalated to cases
     */
    alerts_escalated?: number;
    /**
     * Alerts that received triage action
     */
    alerts_triaged?: number;
    /**
     * Median time to triage (seconds)
     */
    mttt_p50_seconds?: (number | null);
    /**
     * Mean time to triage (seconds)
     */
    mttt_mean_seconds?: (number | null);
    /**
     * 95th percentile time to triage (seconds)
     */
    mttt_p95_seconds?: (number | null);
    /**
     * Total cases created
     */
    case_count?: number;
    /**
     * Cases closed
     */
    cases_closed?: number;
    /**
     * Cases in NEW status
     */
    cases_new?: number;
    /**
     * Cases in IN_PROGRESS status
     */
    cases_in_progress?: number;
    /**
     * Median time to resolution (seconds)
     */
    mttr_p50_seconds?: (number | null);
    /**
     * Mean time to resolution (seconds)
     */
    mttr_mean_seconds?: (number | null);
    /**
     * 95th percentile time to resolution (seconds)
     */
    mttr_p95_seconds?: (number | null);
    /**
     * Total tasks created
     */
    task_count?: number;
    /**
     * Tasks completed
     */
    tasks_completed?: number;
    /**
     * Tasks in TODO status
     */
    tasks_todo?: number;
    /**
     * Tasks in IN_PROGRESS status
     */
    tasks_in_progress?: number;
};

