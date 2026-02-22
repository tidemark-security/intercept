/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for accepting a triage recommendation.
 */
export type AcceptRecommendationRequest = {
    /**
     * Apply suggested status change
     */
    apply_status?: boolean;
    /**
     * Apply suggested priority change
     */
    apply_priority?: boolean;
    /**
     * Apply suggested assignee change
     */
    apply_assignee?: boolean;
    /**
     * Apply suggested tag changes
     */
    apply_tags?: boolean;
};

