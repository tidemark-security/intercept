/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EntityType } from '../models/EntityType';
import type { PaginatedSearchResponse } from '../models/PaginatedSearchResponse';
import type { QueueSearchResponse } from '../models/QueueSearchResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SearchService {
    /**
     * Unified search across all entity types
     * Performs a paginated full-text search across alerts, cases, and tasks.
     * Results are ranked by relevance with title matches weighted highest,
     * followed by description, then timeline content.
     *
     * Supports fuzzy matching for typo tolerance when exact matches fail.
     * @returns PaginatedSearchResponse Successful Response
     * @throws ApiError
     */
    public static unifiedSearchApiV1SearchGet({
        q,
        entityType,
        skip,
        limit = 20,
        startDate,
        endDate,
        allTime = false,
        tags,
    }: {
        /**
         * Search query text (2-200 characters), or '*' for filter-only search
         */
        q: string,
        /**
         * Entity type(s) to search. Can be specified multiple times. Defaults to all types if not provided.
         */
        entityType?: (Array<EntityType> | null),
        /**
         * Number of results to skip (offset for pagination)
         */
        skip?: number,
        /**
         * Maximum results to return (1-100)
         */
        limit?: number,
        /**
         * Start of date range (ISO8601 with Z suffix). Default: 30 days ago
         */
        startDate?: (string | null),
        /**
         * End of date range (ISO8601 with Z suffix). Default: now
         */
        endDate?: (string | null),
        /**
         * Search all dates without the default 30-day window. Cannot be combined with date bounds.
         */
        allTime?: boolean,
        /**
         * Tag filter values. Can be specified multiple times. Matches top-level and timeline item tags (OR semantics).
         */
        tags?: (Array<string> | null),
    }): CancelablePromise<PaginatedSearchResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/search',
            query: {
                'q': q,
                'entity_type': entityType,
                'skip': skip,
                'limit': limit,
                'start_date': startDate,
                'end_date': endDate,
                'all_time': allTime,
                'tags': tags,
            },
            errors: {
                400: `Invalid request parameters`,
                401: `Not authenticated`,
                422: `Validation Error`,
                500: `Internal server error`,
            },
        });
    }
    /**
     * Search within an entity queue
     * Return matching rows with queue filters and ordering, without global defaults.
     * @returns QueueSearchResponse Successful Response
     * @throws ApiError
     */
    public static queueSearchApiV1SearchQueueGet({
        q,
        entityType,
        status,
        assignee,
        includeTags,
        excludeTags,
        startDate,
        endDate,
        sortBy = 'created_at',
        sortOrder = 'desc',
        skip,
        limit = 50,
    }: {
        /**
         * Search text (2–200 characters)
         */
        q: string,
        entityType: EntityType,
        status?: (Array<string> | null),
        assignee?: (Array<string> | null),
        includeTags?: (Array<string> | null),
        excludeTags?: (Array<string> | null),
        startDate?: (string | null),
        endDate?: (string | null),
        sortBy?: 'created_at' | 'updated_at' | 'priority' | 'status',
        sortOrder?: 'asc' | 'desc',
        skip?: number,
        limit?: number,
    }): CancelablePromise<QueueSearchResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/search/queue',
            query: {
                'q': q,
                'entity_type': entityType,
                'status': status,
                'assignee': assignee,
                'include_tags': includeTags,
                'exclude_tags': excludeTags,
                'start_date': startDate,
                'end_date': endDate,
                'sort_by': sortBy,
                'sort_order': sortOrder,
                'skip': skip,
                'limit': limit,
            },
            errors: {
                400: `Bad Request`,
                401: `Not authenticated`,
                422: `Validation Error`,
            },
        });
    }
}
