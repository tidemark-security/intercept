/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Admin request payload for ServiceNow enrichment configuration.
 */
export type ServiceNowConfigureRequest = {
    instance_url: string;
    username: string;
    password?: string;
    auth_type?: string;
    oauth_client_id?: string;
    oauth_client_secret?: string;
    user_table_enabled?: boolean;
    user_table?: string;
    user_query_field?: string;
    user_vip_field?: string;
    user_privileged_field?: string;
    cmdb_table_enabled?: boolean;
    cmdb_table?: string;
    cmdb_query_field?: string;
    cmdb_criticality_field?: string;
    cmdb_privileged_field?: string;
    active_only?: boolean;
    ttl_seconds?: number;
    enabled?: boolean;
};

