/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseAlertClosureUpdate } from './CaseAlertClosureUpdate';
/**
 * Closure resolutions to apply to selected open alerts linked to a case.
 */
export type CaseLinkedAlertResolutionRequest = {
    alert_updates: Array<CaseAlertClosureUpdate>;
    note?: (string | null);
};

