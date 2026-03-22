/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseAlertClosureUpdate } from './CaseAlertClosureUpdate';
import type { CaseStatus } from './CaseStatus';
import type { Priority } from './Priority';
/**
 * Schema for updating a case.
 */
export type CaseUpdate = {
    title?: (string | null);
    description?: (string | null);
    status?: (CaseStatus | null);
    priority?: (Priority | null);
    assignee?: (string | null);
    tags?: (Array<string> | null);
    timeline_items?: null;
    alert_closure_updates?: (Array<CaseAlertClosureUpdate> | null);
};

