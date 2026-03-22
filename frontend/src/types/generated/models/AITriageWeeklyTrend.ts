/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Weekly trend data for AI triage accuracy.
 */
export type AITriageWeeklyTrend = {
    /**
     * Start of the week (Monday)
     */
    week_start: string;
    /**
     * Total recommendations made
     */
    total_recommendations?: number;
    /**
     * Recommendations accepted
     */
    accepted?: number;
    /**
     * Recommendations rejected
     */
    rejected?: number;
    /**
     * Acceptance rate (0-1)
     */
    acceptance_rate?: (number | null);
};

