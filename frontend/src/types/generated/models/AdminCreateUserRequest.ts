/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserRole } from './UserRole';
/**
 * Request to create a new user account with temporary credentials.
 */
export type AdminCreateUserRequest = {
    /**
     * Unique username
     */
    username: string;
    /**
     * User email for notifications
     */
    email: string;
    /**
     * User role (ANALYST, ADMIN, AUDITOR)
     */
    role: UserRole;
    /**
     * User title or role description
     */
    description?: (string | null);
};

