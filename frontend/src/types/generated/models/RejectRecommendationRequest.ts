/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RejectionCategory } from './RejectionCategory';
/**
 * Request body for rejecting a triage recommendation.
 */
export type RejectRecommendationRequest = {
    /**
     * Rejection category (required)
     */
    category: RejectionCategory;
    /**
     * Additional details (optional, required if category is OTHER)
     */
    reason?: (string | null);
};

