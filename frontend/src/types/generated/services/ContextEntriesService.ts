/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ContextEntryCreate } from '../models/ContextEntryCreate';
import type { ContextEntryRead } from '../models/ContextEntryRead';
import type { ContextEntryUpdate } from '../models/ContextEntryUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ContextEntriesService {
    /**
     * List Context Entries
     * List shared context entries.
     * @returns ContextEntryRead Successful Response
     * @throws ApiError
     */
    public static listContextEntriesApiV1ContextEntriesGet({
        includeExpired = false,
    }: {
        includeExpired?: boolean,
    }): CancelablePromise<Array<ContextEntryRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/context-entries',
            query: {
                'include_expired': includeExpired,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Context Entry
     * Create shared context.
     * @returns ContextEntryRead Successful Response
     * @throws ApiError
     */
    public static createContextEntryApiV1ContextEntriesPost({
        requestBody,
    }: {
        requestBody: ContextEntryCreate,
    }): CancelablePromise<ContextEntryRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/context-entries',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Context Entry
     * Edit shared context.
     * @returns ContextEntryRead Successful Response
     * @throws ApiError
     */
    public static updateContextEntryApiV1ContextEntriesEntryIdPut({
        entryId,
        requestBody,
    }: {
        entryId: number,
        requestBody: ContextEntryUpdate,
    }): CancelablePromise<ContextEntryRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/context-entries/{entry_id}',
            path: {
                'entry_id': entryId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Expire Context Entry
     * Expire shared context immediately.
     * @returns ContextEntryRead Successful Response
     * @throws ApiError
     */
    public static expireContextEntryApiV1ContextEntriesEntryIdExpirePost({
        entryId,
    }: {
        entryId: number,
    }): CancelablePromise<ContextEntryRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/context-entries/{entry_id}/expire',
            path: {
                'entry_id': entryId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
