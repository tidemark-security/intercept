/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseTemplateApplyTaskWarning } from './CaseTemplateApplyTaskWarning';
export type CaseTemplateApplyResponse = {
    case_id: number;
    case_human_id: string;
    template_id: number;
    template_human_id: string;
    created_task_ids: Array<number>;
    skipped_task_titles: Array<string>;
    duplicate_warnings?: Array<CaseTemplateApplyTaskWarning>;
};

