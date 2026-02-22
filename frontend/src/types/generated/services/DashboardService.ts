/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardStatsResponse } from '../models/DashboardStatsResponse';
import type { RecentItemsResponse } from '../models/RecentItemsResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DashboardService {
    /**
     * Get Dashboard Stats
     * Get dashboard statistics.
     *
     * Returns counts for:
     * - Unacknowledged alerts (NEW status)
     * - Open tasks (TODO or IN_PROGRESS)
     * - Assigned cases (NEW or IN_PROGRESS)
     * - Tasks due today
     * - Critical cases (CRITICAL or EXTREME priority)
     *
     * If my_items=true (default), stats are filtered to current user's assignments.
     * @returns DashboardStatsResponse Successful Response
     * @throws ApiError
     */
    public static getDashboardStatsApiV1DashboardStatsGet({
        myItems = true,
    }: {
        /**
         * If true, filter stats to current user's assignments only
         */
        myItems?: boolean,
    }): CancelablePromise<DashboardStatsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/dashboard/stats',
            query: {
                'my_items': myItems,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Recent Items
     * Get recently updated items (alerts, cases, tasks).
     *
     * Returns items sorted by updated_at descending.
     * If my_items=true (default), only items assigned to current user are returned.
     * @returns RecentItemsResponse Successful Response
     * @throws ApiError
     */
    public static getRecentItemsApiV1DashboardRecentGet({
        limit = 10,
        myItems = true,
    }: {
        /**
         * Maximum number of items to return
         */
        limit?: number,
        /**
         * If true, filter to current user's assignments only
         */
        myItems?: boolean,
    }): CancelablePromise<RecentItemsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/dashboard/recent',
            query: {
                'limit': limit,
                'my_items': myItems,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Priority Items
     * Get open items assigned to current user (My Open Items).
     *
     * Returns all open alerts, cases, and tasks assigned to the current user,
     * sorted by priority (highest first), then by type (alerts, tasks, cases).
     * This helps analysts see their workload prioritized.
     * @returns RecentItemsResponse Successful Response
     * @throws ApiError
     */
    public static getPriorityItemsApiV1DashboardPriorityItemsGet({
        limit = 100,
    }: {
        /**
         * Maximum number of items to return
         */
        limit?: number,
    }): CancelablePromise<RecentItemsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/dashboard/priority-items',
            query: {
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
