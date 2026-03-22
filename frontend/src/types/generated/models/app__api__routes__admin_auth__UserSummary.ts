/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccountType } from './AccountType';
import type { UserRole } from './UserRole';
/**
 * Lightweight user summary for dropdowns and listings.
 */
export type app__api__routes__admin_auth__UserSummary = {
    /**
     * User ID
     */
    userId: string;
    /**
     * Username
     */
    username: string;
    /**
     * User email
     */
    email: (string | null);
    /**
     * User role
     */
    role: UserRole;
    /**
     * Account type (HUMAN, NHI)
     */
    accountType: AccountType;
    /**
     * OIDC issuer for linked SSO identities
     */
    oidcIssuer?: (string | null);
    /**
     * OIDC subject for linked SSO identities
     */
    oidcSubject?: (string | null);
};

