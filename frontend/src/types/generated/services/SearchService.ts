/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EntityType } from '../models/EntityType';
import type { PaginatedSearchResponse } from '../models/PaginatedSearchResponse';
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
}
