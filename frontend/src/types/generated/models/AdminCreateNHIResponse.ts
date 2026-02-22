/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiKeyCreateResponse } from './ApiKeyCreateResponse';
import type { UserRole } from './UserRole';
/**
 * Response after successful NHI account creation.
 */
export type AdminCreateNHIResponse = {
    /**
     * ID of the created NHI account
     */
    userId: string;
    /**
     * Username of the NHI account
     */
    username: string;
    /**
     * Role assigned to the NHI account
     */
    role: UserRole;
    /**
     * Initial API key (only shown once)
     */
    apiKey: ApiKeyCreateResponse;
};

