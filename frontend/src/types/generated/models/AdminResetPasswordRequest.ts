/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ResetDeliveryChannel } from './ResetDeliveryChannel';
/**
 * Request to issue an admin-initiated password reset.
 */
export type AdminResetPasswordRequest = {
    /**
     * Target user ID
     */
    userId: string;
    /**
     * Delivery channel for temporary credential
     */
    deliveryChannel?: ResetDeliveryChannel;
};

