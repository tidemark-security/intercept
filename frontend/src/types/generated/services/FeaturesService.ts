/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureFlags } from '../models/FeatureFlags';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class FeaturesService {
    /**
     * Get Feature Flags
     * Get public feature flags.
     *
     * No authentication required - returns only non-sensitive feature states.
     * This endpoint is designed to be called by the frontend to determine
     * which features should be displayed.
     * @returns FeatureFlags Successful Response
     * @throws ApiError
     */
    public static getFeatureFlagsApiV1FeaturesGet(): CancelablePromise<FeatureFlags> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/features',
        });
    }
}
