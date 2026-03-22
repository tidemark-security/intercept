/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for reading API key metadata (never includes the actual key).
 */
export type ApiKeyRead = {
    /**
     * User-defined name for this API key
     */
    name: string;
    /**
     * Expiration date (required for all API keys)
     */
    expires_at: string;
    id: string;
    user_id: string;
    prefix: string;
    last_used_at: (string | null);
    revoked_at: (string | null);
    created_at: string;
};

