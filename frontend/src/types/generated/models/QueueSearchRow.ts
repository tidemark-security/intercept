/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
import type { CaseStatus } from './CaseStatus';
import type { Priority } from './Priority';
import type { TaskStatus } from './TaskStatus';
/**
 * List-card and bulk-selection metadata without timeline or detail payloads.
 */
export type QueueSearchRow = {
    id: number;
    human_id: string;
    title: string;
    created_at: string;
    updated_at?: (string | null);
    status: (AlertStatus | CaseStatus | TaskStatus);
    priority?: (Priority | null);
    assignee?: (string | null);
    tags?: Array<string>;
    case_id?: (number | null);
};

