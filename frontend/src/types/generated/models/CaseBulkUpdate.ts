/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseStatus } from './CaseStatus';
import type { TaskStatus } from './TaskStatus';
/**
 * Apply optional status, assignee, tags and a note to the selected cases.
 */
export type CaseBulkUpdate = {
    entity_ids: Array<number>;
    status?: (CaseStatus | TaskStatus | null);
    assignee?: (string | null);
    tags?: (Array<string> | null);
    note?: (string | null);
};

