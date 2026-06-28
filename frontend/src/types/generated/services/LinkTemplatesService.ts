/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LinkTemplateCreate } from '../models/LinkTemplateCreate';
import type { LinkTemplateExportBundle } from '../models/LinkTemplateExportBundle';
import type { LinkTemplateExportRequest } from '../models/LinkTemplateExportRequest';
import type { LinkTemplateRead } from '../models/LinkTemplateRead';
import type { LinkTemplateResolveRequest } from '../models/LinkTemplateResolveRequest';
import type { LinkTemplateUpdate } from '../models/LinkTemplateUpdate';
import type { ResolvedLinkTemplateRead } from '../models/ResolvedLinkTemplateRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class LinkTemplatesService {
    /**
     * Get Link Templates
     * Get public link templates.
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
     * Create a public link template.
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
     * Export Link Templates
     * Export selected public link templates as a portable JSON bundle.
     * @returns LinkTemplateExportBundle Successful Response
     * @throws ApiError
     */
    public static exportLinkTemplatesApiV1LinkTemplatesExportPost({
        requestBody,
    }: {
        requestBody: LinkTemplateExportRequest,
    }): CancelablePromise<LinkTemplateExportBundle> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/link-templates/export',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Import Link Templates
     * Import public link templates from a portable single-template or bundle payload.
     * @returns LinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static importLinkTemplatesApiV1LinkTemplatesImportPost({
        requestBody,
    }: {
        requestBody: any,
    }): CancelablePromise<Array<LinkTemplateRead>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/link-templates/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resolve Link Templates
     * Resolve enabled public and current-user personal templates for one context.
     * @returns ResolvedLinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static resolveLinkTemplatesApiV1LinkTemplatesResolvePost({
        requestBody,
    }: {
        requestBody: LinkTemplateResolveRequest,
    }): CancelablePromise<Array<ResolvedLinkTemplateRead>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/link-templates/resolve',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Link Template
     * Get one public link template.
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
     * Update a public link template.
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
     * Delete a public link template.
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
