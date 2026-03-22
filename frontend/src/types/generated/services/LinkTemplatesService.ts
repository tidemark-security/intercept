/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LinkTemplateCreate } from '../models/LinkTemplateCreate';
import type { LinkTemplateRead } from '../models/LinkTemplateRead';
import type { LinkTemplateUpdate } from '../models/LinkTemplateUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class LinkTemplatesService {
    /**
     * Get Link Templates
     * Get all link templates.
     *
     * Args:
     * enabled_only: If True, only return enabled templates (default: True)
     * db: Database session
     *
     * Returns:
     * List of link templates ordered by display_order
     * @returns LinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static getLinkTemplatesApiV1LinkTemplatesGet({
        enabledOnly = true,
    }: {
        enabledOnly?: boolean,
    }): CancelablePromise<Array<LinkTemplateRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/link-templates',
            query: {
                'enabled_only': enabledOnly,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Link Template
     * Create a new link template.
     *
     * Args:
     * template_data: Link template data
     * db: Database session
     *
     * Returns:
     * Created link template
     * @returns LinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static createLinkTemplateApiV1LinkTemplatesPost({
        requestBody,
    }: {
        requestBody: LinkTemplateCreate,
    }): CancelablePromise<LinkTemplateRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/link-templates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Link Template
     * Get a specific link template by ID.
     *
     * Args:
     * template_id: Database ID of the template
     * db: Database session
     *
     * Returns:
     * Link template details
     * @returns LinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static getLinkTemplateApiV1LinkTemplatesTemplateIdGet({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<LinkTemplateRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/link-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Link Template
     * Update a link template.
     *
     * Args:
     * template_id: Database ID of the template
     * template_data: Updated template data
     * db: Database session
     *
     * Returns:
     * Updated link template
     * @returns LinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static updateLinkTemplateApiV1LinkTemplatesTemplateIdPatch({
        templateId,
        requestBody,
    }: {
        templateId: number,
        requestBody: LinkTemplateUpdate,
    }): CancelablePromise<LinkTemplateRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/link-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Link Template
     * Delete a link template.
     *
     * Args:
     * template_id: Database ID of the template
     * db: Database session
     *
     * Returns:
     * Success message
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteLinkTemplateApiV1LinkTemplatesTemplateIdDelete({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/link-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
