/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
import type { Priority } from './Priority';
import type { RecommendationStatus } from './RecommendationStatus';
import type { RejectionCategory } from './RejectionCategory';
import type { TriageDisposition } from './TriageDisposition';
/**
 * Schema for reading a triage recommendation.
 */
export type TriageRecommendationRead = {
    id: number;
    alert_id: number;
    disposition: TriageDisposition;
    confidence: number;
    reasoning_bullets?: Array<string>;
    recommended_actions?: Array<any>;
    suggested_status?: (AlertStatus | null);
    suggested_priority?: (Priority | null);
    suggested_assignee?: (string | null);
    suggested_tags_add?: Array<string>;
    suggested_tags_remove?: Array<string>;
    request_escalate_to_case?: boolean;
    created_by: string;
    created_at: string;
    status: RecommendationStatus;
    reviewed_by?: (string | null);
    reviewed_at?: (string | null);
    rejection_category?: (RejectionCategory | null);
    rejection_reason?: (string | null);
    applied_changes?: Array<Record<string, any>>;
    error_message?: (string | null);
};

