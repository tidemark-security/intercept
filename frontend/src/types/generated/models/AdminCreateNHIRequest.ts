/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserRole } from './UserRole';
/**
 * Request to create a Non-Human Identity (NHI) account.
 */
export type AdminCreateNHIRequest = {
    /**
     * Unique username for the NHI account
     */
    username: string;
    /**
     * User role (ANALYST, ADMIN, AUDITOR)
     */
    role: UserRole;
    /**
     * Purpose or description of this NHI account
     */
    description?: (string | null);
    /**
     * Name for the initial API key
     */
    initial_api_key_name: string;
    /**
     * Expiration date for the initial API key (required)
     */
    initial_api_key_expires_at: string;
};

