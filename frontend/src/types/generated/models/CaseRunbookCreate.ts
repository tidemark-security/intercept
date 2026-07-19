/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseRunbookStatus } from './CaseRunbookStatus';
import type { RunbookTaskDefinition } from './RunbookTaskDefinition';
export type CaseRunbookCreate = {
    title?: (string | null);
    description?: (string | null);
    status?: (CaseRunbookStatus | null);
    case_tags?: Array<string>;
    runbook_tasks?: Array<RunbookTaskDefinition>;
};

