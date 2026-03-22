/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response after successful password reset issuance.
 */
export type AdminResetPasswordResponse = {
    /**
     * ID of the reset request
     */
    resetRequestId: string;
    /**
     * Expiration timestamp for password reset token
     */
    expiresAt: string;
    /**
     * One-time password reset token
     */
    resetToken: string;
};

