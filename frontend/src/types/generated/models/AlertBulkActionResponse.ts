/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertRead } from './AlertRead';
/**
 * Response for bulk alert actions.
 */
export type AlertBulkActionResponse = {
    updated_alerts: Array<AlertRead>;
    updated_count: number;
    case_id?: (number | null);
    case_human_id?: (string | null);
};

