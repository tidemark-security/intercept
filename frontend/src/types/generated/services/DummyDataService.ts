/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DummyDataService {
    /**
     * Populate Dummy Data
     * Populate the database with randomized dummy data for development and testing.
     *
     * This endpoint creates realistic test data including:
     * - Cases with randomized titles, descriptions, statuses, and timeline items
     * - Alerts with various severities, statuses, and indicators
     * - Relationships between some alerts and cases
     *
     * **Warning**: This is intended for development environments only.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static populateDummyDataApiV1DummyDataPopulatePost({
        casesCount = 10,
        alertsCount = 20,
        linkAlerts = true,
    }: {
        /**
         * Number of cases to create
         */
        casesCount?: number,
        /**
         * Number of random alerts to create (closure-prone alerts are added automatically)
         */
        alertsCount?: number,
        /**
         * Whether to link some alerts to cases
         */
        linkAlerts?: boolean,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/dummy-data/populate',
            query: {
                'cases_count': casesCount,
                'alerts_count': alertsCount,
                'link_alerts': linkAlerts,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Clear All Data
     * Clear dummy data (tagged with ``tmi_dummy_data``) from the database.
     *
     * **Only** cases, alerts, tasks, and related audit logs that were created
     * by the dummy-data service are removed.  User-created data is untouched.
     *
     * Requires confirmation parameter to be set to true.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static clearAllDataApiV1DummyDataClearDelete({
        confirm = false,
    }: {
        /**
         * Must be true to confirm data deletion
         */
        confirm?: boolean,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/dummy-data/clear',
            query: {
                'confirm': confirm,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Cases Only
     * Generate only cases with timeline items (no alerts).
     *
     * Useful for testing case-specific functionality without cluttering
     * the alerts list.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static generateCasesOnlyApiV1DummyDataGenerateCasesPost({
        count = 5,
    }: {
        /**
         * Number of cases to create
         */
        count?: number,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/dummy-data/generate-cases',
            query: {
                'count': count,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Alerts Only
     * Generate only alerts (not linked to cases).
     *
     * Useful for testing alert triage functionality and alert list views.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static generateAlertsOnlyApiV1DummyDataGenerateAlertsPost({
        count = 10,
    }: {
        /**
         * Number of random alerts to create (closure-prone alerts are added automatically)
         */
        count?: number,
    }): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/dummy-data/generate-alerts',
            query: {
                'count': count,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Data Stats
     * Get statistics about current data in the database.
     *
     * Returns counts of cases, alerts, and their relationships.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getDataStatsApiV1DummyDataStatsGet(): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/dummy-data/stats',
        });
    }
}
