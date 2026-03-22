/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request to create a new API key.
 */
export type CreateApiKeyRequest = {
    /**
     * User-defined name for this API key
     */
    name: string;
    /**
     * Expiration date (required)
     */
    expires_at: string;
    /**
     * Target user ID (admin-only, defaults to current user)
     */
    user_id?: (string | null);
};

