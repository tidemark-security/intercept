/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Aggregated SOC metrics summary across the query time range.
 */
export type SOCMetricsSummary = {
    /**
     * Total alerts in period
     */
    total_alerts?: number;
    /**
     * Total alerts closed
     */
    total_alerts_closed?: number;
    /**
     * Total true positives
     */
    total_alerts_tp?: number;
    /**
     * Total false positives
     */
    total_alerts_fp?: number;
    /**
     * Total benign positives
     */
    total_alerts_bp?: number;
    /**
     * True positive rate (TP / closed)
     */
    tp_rate?: (number | null);
    /**
     * False positive rate (FP / closed)
     */
    fp_rate?: (number | null);
    /**
     * Benign positive rate (BP / closed)
     */
    bp_rate?: (number | null);
    /**
     * Escalation rate (escalated / triaged)
     */
    escalation_rate?: (number | null);
    /**
     * Overall median MTTT
     */
    mttt_p50_seconds?: (number | null);
    /**
     * Overall mean MTTT
     */
    mttt_mean_seconds?: (number | null);
    /**
     * Overall median MTTR
     */
    mttr_p50_seconds?: (number | null);
    /**
     * Overall mean MTTR
     */
    mttr_mean_seconds?: (number | null);
    /**
     * Total cases in period
     */
    total_cases?: number;
    /**
     * Total cases closed
     */
    total_cases_closed?: number;
    /**
     * Currently open cases
     */
    open_cases?: number;
    /**
     * Total tasks in period
     */
    total_tasks?: number;
    /**
     * Total tasks completed
     */
    total_tasks_completed?: number;
    /**
     * Currently open tasks
     */
    open_tasks?: number;
};

