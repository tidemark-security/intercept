/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseRunbookApplyTaskWarning } from './CaseRunbookApplyTaskWarning';
export type CaseRunbookApplyResponse = {
    case_id: number;
    case_human_id: string;
    runbook_id: number;
    runbook_human_id: string;
    created_task_ids: Array<number>;
    skipped_task_titles: Array<string>;
    duplicate_warnings?: Array<CaseRunbookApplyTaskWarning>;
};

