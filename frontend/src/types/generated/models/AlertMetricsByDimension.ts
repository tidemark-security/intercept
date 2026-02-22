/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Alert metrics aggregated by a generic dimension (source, title, or tag).
 */
export type AlertMetricsByDimension = {
    /**
     * Dimension type: 'source', 'title', or 'tag'
     */
    dimension: string;
    /**
     * Dimension value
     */
    value?: (string | null);
    /**
     * Total alerts
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
     * Total benign positives
     */
    total_bp?: number;
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

