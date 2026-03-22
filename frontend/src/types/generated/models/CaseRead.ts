/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseStatus } from './CaseStatus';
import type { Priority } from './Priority';
/**
 * Schema for reading a case.
 */
export type CaseRead = {
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
    readonly human_id: string;
};

