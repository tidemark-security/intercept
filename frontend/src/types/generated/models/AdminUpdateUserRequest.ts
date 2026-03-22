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
     * Updated user title or service account description
     */
    description?: (string | null);
};

