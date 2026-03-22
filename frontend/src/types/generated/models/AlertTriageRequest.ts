/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
/**
 * Schema for triaging an alert.
 */
export type AlertTriageRequest = {
    status: AlertStatus;
    triage_notes?: (string | null);
    escalate_to_case?: boolean;
    case_title?: (string | null);
    case_description?: (string | null);
};

