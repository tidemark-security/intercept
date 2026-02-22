/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TriageRecommendationDetail } from './TriageRecommendationDetail';
/**
 * Paginated response for triage recommendation drill-down.
 */
export type TriageRecommendationDrillDownResponse = {
    items?: Array<TriageRecommendationDetail>;
    /**
     * Total count matching filters
     */
    total?: number;
    limit?: number;
    offset?: number;
};

