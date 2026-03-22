/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
import type { Priority } from './Priority';
import type { TriageRecommendationRead } from './TriageRecommendationRead';
/**
 * Schema for reading an alert.
 */
export type AlertRead = {
    title: string;
    description?: (string | null);
    priority?: (Priority | null);
    source?: (string | null);
    id: number;
    status: AlertStatus;
    assignee?: (string | null);
    triaged_at?: (string | null);
    triage_notes?: (string | null);
    case_id?: (number | null);
    linked_at?: (string | null);
    created_at: string;
    updated_at: string;
    timeline_items?: null;
    tags?: (Array<string> | null);
    triage_recommendation?: (TriageRecommendationRead | null);
    readonly human_id: string;
};

