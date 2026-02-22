/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for reading audit logs.
 */
export type CaseAuditLogRead = {
    id: number;
    action: string;
    description?: (string | null);
    old_value?: (string | null);
    new_value?: (string | null);
    performed_by: string;
    performed_at: string;
};

