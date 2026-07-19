/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserRole } from './UserRole';
/**
 * Request to update editable user account fields.
 */
export type AdminUpdateUserRequest = {
    /**
     * Updated unique username
     */
    username?: (string | null);
    /**
     * Updated email for human accounts
     */
    email?: (string | null);
    /**
     * Updated user role
     */
    role?: (UserRole | null);
    /**
     * Whether an NHI account can be assigned task work
     */
    assignable?: boolean;
    /**
     * Whether an NHI account can override created_at timestamps during migration imports
     */
    override_timestamps?: boolean;
    /**
     * Updated user title or service account description
     */
    description?: (string | null);
};

