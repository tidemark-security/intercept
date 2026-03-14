/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EnrichmentAliasRead } from '../models/EnrichmentAliasRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class EnrichmentsService {
    /**
     * Search Aliases
     * @returns EnrichmentAliasRead Successful Response
     * @throws ApiError
     */
    public static searchAliasesApiV1EnrichmentsAliasesSearchGet({
        q,
        entityType,
        providerId,
        limit = 20,
    }: {
        /**
         * Alias search query
         */
        q: string,
        /**
         * Canonical entity type, such as user or ip
         */
        entityType: string,
        /**
         * Optional provider filter
         */
        providerId?: (string | null),
        limit?: number,
    }): CancelablePromise<Array<EnrichmentAliasRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/enrichments/aliases/search',
            query: {
                'q': q,
                'entity_type': entityType,
                'provider_id': providerId,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Enqueue Item Enrichment
     * @returns any Successful Response
     * @throws ApiError
     */
    public static enqueueItemEnrichmentApiV1EnrichmentsEntityTypeEntityIdItemsItemIdEnqueuePost({
        entityType,
        entityId,
        itemId,
    }: {
        entityType: string,
        entityId: number,
        itemId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/enrichments/{entity_type}/{entity_id}/items/{item_id}/enqueue',
            path: {
                'entity_type': entityType,
                'entity_id': entityId,
                'item_id': itemId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
