/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TriageRecommendationRead } from './TriageRecommendationRead';
/**
 * Response from accepting a triage recommendation.
 */
export type AcceptRecommendationResponse = {
    recommendation: TriageRecommendationRead;
    /**
     * New case ID if escalated
     */
    case_id?: (number | null);
    /**
     * New case human ID if escalated
     */
    case_human_id?: (string | null);
    /**
     * Number of tasks created from recommended actions
     */
    tasks_created?: number;
};

