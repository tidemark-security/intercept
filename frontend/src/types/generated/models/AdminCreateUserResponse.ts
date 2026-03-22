/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response after successful user creation.
 */
export type AdminCreateUserResponse = {
    /**
     * ID of the created user
     */
    userId: string;
    /**
     * Expiration timestamp for password setup token
     */
    expiresAt: string;
    /**
     * One-time password setup token
     */
    resetToken: string;
};

