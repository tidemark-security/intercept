/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UserStatus } from './UserStatus';
/**
 * Request to update user account status.
 */
export type AdminUpdateStatusRequest = {
    /**
     * New status (ACTIVE, DISABLED, LOCKED)
     */
    status: UserStatus;
};

