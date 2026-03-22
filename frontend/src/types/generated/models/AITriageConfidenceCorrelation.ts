/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Confidence score correlation with acceptance.
 */
export type AITriageConfidenceCorrelation = {
    /**
     * Confidence range (e.g., '0.8-0.9')
     */
    confidence_bucket: string;
    /**
     * Total recommendations in bucket
     */
    total?: number;
    /**
     * Accepted recommendations
     */
    accepted?: number;
    /**
     * Rejected recommendations
     */
    rejected?: number;
    /**
     * Acceptance rate for this confidence range
     */
    acceptance_rate?: (number | null);
};

