/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * User-facing connected MCP client metadata.
 */
export type MCPOAuthClientRead = {
    id: string;
    client_id: string;
    client_name: string;
    client_uri?: (string | null);
    redirect_uris?: Array<string>;
    scope: string;
    created_at: string;
    last_authorized_at: string;
    last_used_at?: (string | null);
};

