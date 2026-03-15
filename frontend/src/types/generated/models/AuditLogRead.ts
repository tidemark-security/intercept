/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for reading persisted audit logs.
 */
export type AuditLogRead = {
    id: number;
    event_type: string;
    entity_type?: (string | null);
    entity_id?: (string | null);
    item_id?: (string | null);
    description?: (string | null);
    old_value?: (string | null);
    new_value?: (string | null);
    performed_by?: (string | null);
    performed_at: string;
    ip_address?: (string | null);
    user_agent?: (string | null);
    correlation_id?: (string | null);
};

