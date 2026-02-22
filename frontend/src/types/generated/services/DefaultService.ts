/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Root
     * Root endpoint.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static rootGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/',
        });
    }
    /**
     * Health Check
     * Health check endpoint.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static healthCheckHealthGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/health',
        });
    }
    /**
     * Options Handler
     * Handle CORS preflight requests.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static optionsHandlerPathOptions({
        path,
    }: {
        path: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'OPTIONS',
            url: '/{path}',
            path: {
                'path': path,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
