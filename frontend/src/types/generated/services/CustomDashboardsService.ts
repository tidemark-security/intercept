/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CustomDashboardRead } from '../models/CustomDashboardRead';
import type { DashboardDrillRequest } from '../models/DashboardDrillRequest';
import type { DashboardDuplicate } from '../models/DashboardDuplicate';
import type { DashboardEvaluate } from '../models/DashboardEvaluate';
import type { DashboardEvaluation } from '../models/DashboardEvaluation';
import type { DashboardMeasure } from '../models/DashboardMeasure';
import type { DashboardRecords } from '../models/DashboardRecords';
import type { DashboardSummary } from '../models/DashboardSummary';
import type { DashboardUpdate } from '../models/DashboardUpdate';
import type { DashboardWrite } from '../models/DashboardWrite';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class CustomDashboardsService {
    /**
     * Get Catalog
     * @returns DashboardMeasure Successful Response
     * @throws ApiError
     */
    public static getDashboardCatalog(): CancelablePromise<Array<DashboardMeasure>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/custom-dashboards/catalog',
        });
    }
    /**
     * List Dashboards
     * @returns DashboardSummary Successful Response
     * @throws ApiError
     */
    public static listCustomDashboards(): CancelablePromise<Array<DashboardSummary>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/custom-dashboards',
        });
    }
    /**
     * Create Dashboard
     * @returns CustomDashboardRead Successful Response
     * @throws ApiError
     */
    public static createCustomDashboard({
        requestBody,
    }: {
        requestBody: DashboardWrite,
    }): CancelablePromise<CustomDashboardRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/custom-dashboards',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Evaluate Dashboard
     * @returns DashboardEvaluation Successful Response
     * @throws ApiError
     */
    public static evaluateCustomDashboard({
        requestBody,
    }: {
        requestBody: DashboardEvaluate,
    }): CancelablePromise<DashboardEvaluation> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/custom-dashboards/evaluate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Drill Dashboard
     * @returns DashboardRecords Successful Response
     * @throws ApiError
     */
    public static getDashboardRecords({
        requestBody,
    }: {
        requestBody: DashboardDrillRequest,
    }): CancelablePromise<DashboardRecords> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/custom-dashboards/records',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Dashboard
     * @returns CustomDashboardRead Successful Response
     * @throws ApiError
     */
    public static getCustomDashboard({
        identifier,
    }: {
        identifier: string,
    }): CancelablePromise<CustomDashboardRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/custom-dashboards/{identifier}',
            path: {
                'identifier': identifier,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Dashboard
     * @returns CustomDashboardRead Successful Response
     * @throws ApiError
     */
    public static updateCustomDashboard({
        identifier,
        requestBody,
    }: {
        identifier: string,
        requestBody: DashboardUpdate,
    }): CancelablePromise<CustomDashboardRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/custom-dashboards/{identifier}',
            path: {
                'identifier': identifier,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Dashboard
     * @returns void
     * @throws ApiError
     */
    public static deleteCustomDashboard({
        identifier,
        revision,
    }: {
        identifier: string,
        revision: number,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/custom-dashboards/{identifier}',
            path: {
                'identifier': identifier,
            },
            query: {
                'revision': revision,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Duplicate Dashboard
     * @returns CustomDashboardRead Successful Response
     * @throws ApiError
     */
    public static duplicateCustomDashboard({
        identifier,
        requestBody,
    }: {
        identifier: string,
        requestBody: DashboardDuplicate,
    }): CancelablePromise<CustomDashboardRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/custom-dashboards/{identifier}/duplicate',
            path: {
                'identifier': identifier,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
