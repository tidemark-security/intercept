/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Recommendation breakdown by disposition.
 */
export type AITriageByDisposition = {
    /**
     * Triage disposition
     */
    disposition: string;
    /**
     * Total recommendations with this disposition
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
     * Acceptance rate for this disposition
     */
    acceptance_rate?: (number | null);
};

