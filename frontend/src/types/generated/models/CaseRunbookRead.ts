/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseRunbookStatus } from './CaseRunbookStatus';
import type { RunbookTaskDefinition } from './RunbookTaskDefinition';
export type CaseRunbookRead = {
    title?: (string | null);
    description?: (string | null);
    status?: CaseRunbookStatus;
    case_tags?: Array<string>;
    runbook_tasks?: Array<RunbookTaskDefinition>;
    id: number;
    title_normalized?: (string | null);
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string;
    readonly human_id: string;
};

