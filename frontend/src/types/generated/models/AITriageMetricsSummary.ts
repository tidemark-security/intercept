/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Summary statistics for AI triage accuracy.
 */
export type AITriageMetricsSummary = {
    /**
     * Total recommendations in period
     */
    total_recommendations?: number;
    /**
     * Total accepted
     */
    total_accepted?: number;
    /**
     * Total rejected
     */
    total_rejected?: number;
    /**
     * Currently pending review
     */
    total_pending?: number;
    /**
     * Overall acceptance rate (0-1)
     */
    acceptance_rate?: (number | null);
    /**
     * Overall rejection rate (0-1)
     */
    rejection_rate?: (number | null);
    /**
     * Average confidence score
     */
    avg_confidence?: (number | null);
};

