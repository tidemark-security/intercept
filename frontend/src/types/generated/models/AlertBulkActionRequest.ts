/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
import type { TriageDisposition } from './TriageDisposition';
export type AlertBulkActionRequest = {
    alert_ids: Array<number>;
    action: 'update_status' | 'link_case' | 'create_case' | 'close_duplicate' | 'add_tags';
    status?: (AlertStatus | null);
    disposition?: (TriageDisposition | null);
    case_id?: (number | null);
    case_title?: (string | null);
    case_description?: (string | null);
    tags?: (Array<string> | null);
    duplicate_target_case_id?: (number | null);
    duplicate_target_alert_id?: (number | null);
    note?: (string | null);
};
