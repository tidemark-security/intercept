/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Aggregated metrics for a single analyst.
 */
export type AnalystMetricsSummary = {
    /**
     * Analyst username
     */
    analyst: string;
    /**
     * Total alerts triaged
     */
    total_alerts_triaged?: number;
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
     * Total escalations
     */
    total_alerts_escalated?: number;
    /**
     * Analyst TP rate
     */
    tp_rate?: (number | null);
    /**
     * Analyst FP rate
     */
    fp_rate?: (number | null);
    /**
     * Analyst escalation rate
     */
    escalation_rate?: (number | null);
    /**
     * Analyst median MTTT
     */
    mttt_p50_seconds?: (number | null);
    /**
     * Analyst mean MTTT
     */
    mttt_mean_seconds?: (number | null);
    /**
     * Team median MTTT for comparison
     */
    team_mttt_p50_seconds?: (number | null);
    /**
     * Total cases worked
     */
    total_cases_assigned?: number;
    /**
     * Total cases closed
     */
    total_cases_closed?: number;
    /**
     * Total tasks completed
     */
    total_tasks_completed?: number;
};

