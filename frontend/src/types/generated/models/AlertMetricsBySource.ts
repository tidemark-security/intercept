/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Alert metrics aggregated by source.
 */
export type AlertMetricsBySource = {
    /**
     * Alert source/rule
     */
    source?: (string | null);
    /**
     * Total alerts from source
     */
    total_alerts?: number;
    /**
     * Total closed
     */
    total_closed?: number;
    /**
     * Total true positives
     */
    total_tp?: number;
    /**
     * Total false positives
     */
    total_fp?: number;
    /**
     * Total escalated
     */
    total_escalated?: number;
    /**
     * Overall FP rate
     */
    fp_rate?: (number | null);
    /**
     * Overall escalation rate
     */
    escalation_rate?: (number | null);
};

