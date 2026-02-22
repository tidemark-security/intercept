/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ResetDeliveryChannel } from './ResetDeliveryChannel';
/**
 * Response after successful user creation.
 */
export type AdminCreateUserResponse = {
    /**
     * ID of the created user
     */
    userId: string;
    /**
     * Expiration timestamp for temporary credential
     */
    temporaryCredentialExpiresAt: string;
    /**
     * Channel used to deliver temporary credential
     */
    deliveryChannel: ResetDeliveryChannel;
};

