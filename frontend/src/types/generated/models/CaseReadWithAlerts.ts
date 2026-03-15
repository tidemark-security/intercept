/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertRead } from './AlertRead';
import type { CaseStatus } from './CaseStatus';
import type { Priority } from './Priority';
/**
 * Case with alerts.
 */
export type CaseReadWithAlerts = {
    title: string;
    description?: (string | null);
    priority?: Priority;
    tags?: (Array<string> | null);
    id: number;
    status: CaseStatus;
    assignee?: (string | null);
    created_by: string;
    created_at: string;
    updated_at: string;
    closed_at?: (string | null);
    timeline_items?: null;
    alerts?: Array<AlertRead>;
    readonly human_id: string;
};

