/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SavedFilterCreate } from '../models/SavedFilterCreate';
import type { SavedFilterQueue } from '../models/SavedFilterQueue';
import type { SavedFilterRead } from '../models/SavedFilterRead';
import type { SavedFilterRename } from '../models/SavedFilterRename';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SavedFiltersService {
    /**
     * List Saved Filters
     * List the user's personal filters and organization filters for one queue.
     * @returns SavedFilterRead Successful Response
     * @throws ApiError
     */
    public static listSavedFilters({
        queue,
    }: {
        queue: SavedFilterQueue,
    }): CancelablePromise<Array<SavedFilterRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/saved-filters',
            query: {
                'queue': queue,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Saved Filter
     * Create a saved filter in the selected scope.
     * @returns SavedFilterRead Successful Response
     * @throws ApiError
     */
    public static createSavedFilter({
        requestBody,
    }: {
        requestBody: SavedFilterCreate,
    }): CancelablePromise<SavedFilterRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/saved-filters',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Rename Saved Filter
     * Rename a saved filter.
     * @returns SavedFilterRead Successful Response
     * @throws ApiError
     */
    public static renameSavedFilter({
        filterId,
        requestBody,
    }: {
        filterId: string,
        requestBody: SavedFilterRename,
    }): CancelablePromise<SavedFilterRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/saved-filters/{filter_id}',
            path: {
                'filter_id': filterId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Saved Filter
     * Delete a saved filter.
     * @returns void
     * @throws ApiError
     */
    public static deleteSavedFilter({
        filterId,
    }: {
        filterId: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/saved-filters/{filter_id}',
            path: {
                'filter_id': filterId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
