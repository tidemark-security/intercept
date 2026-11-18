/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserRole } from './UserRole';
/**
 * Request to pre-provision an OIDC-only human account.
 */
export type AdminCreateOIDCUserRequest = {
    /**
     * Unique username
     */
    username: string;
    /**
     * Optional user email
     */
    email?: (string | null);
    /**
     * User role (ANALYST, ADMIN, AUDITOR)
     */
    role: UserRole;
    /**
     * User title or role description
     */
    description?: (string | null);
    /**
     * Exact case-sensitive OIDC issuer
     */
    oidc_issuer: string;
    /**
     * Exact case-sensitive OIDC subject
     */
    oidc_subject: string;
};

