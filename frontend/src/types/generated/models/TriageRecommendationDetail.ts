/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RecommendationStatus } from './RecommendationStatus';
import type { RejectionCategory } from './RejectionCategory';
import type { TriageDisposition } from './TriageDisposition';
/**
 * Triage recommendation with linked alert summary for drill-down reports.
 */
export type TriageRecommendationDetail = {
    id: number;
    alert_id: number;
    /**
     * Human-readable alert ID (e.g., ALT-0000001)
     */
    alert_human_id: string;
    /**
     * Alert title
     */
    alert_title: string;
    /**
     * Alert source
     */
    alert_source?: (string | null);
    disposition: TriageDisposition;
    confidence: number;
    status: RecommendationStatus;
    rejection_category?: (RejectionCategory | null);
    rejection_reason?: (string | null);
    reviewed_by?: (string | null);
    reviewed_at?: (string | null);
    created_at: string;
};

