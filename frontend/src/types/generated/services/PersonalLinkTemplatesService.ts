/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LinkTemplateExportBundle } from '../models/LinkTemplateExportBundle';
import type { LinkTemplateExportRequest } from '../models/LinkTemplateExportRequest';
import type { PersonalLinkTemplateCreate } from '../models/PersonalLinkTemplateCreate';
import type { PersonalLinkTemplateRead } from '../models/PersonalLinkTemplateRead';
import type { PersonalLinkTemplateUpdate } from '../models/PersonalLinkTemplateUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class PersonalLinkTemplatesService {
    /**
     * Get Personal Link Templates
     * Get the current user's personal link templates.
     * @returns PersonalLinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static getPersonalLinkTemplatesApiV1PersonalLinkTemplatesGet({
        enabledOnly = false,
    }: {
        enabledOnly?: boolean,
    }): CancelablePromise<Array<PersonalLinkTemplateRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/personal-link-templates',
            query: {
                'enabled_only': enabledOnly,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Personal Link Template
     * Create a current-user personal link template.
     * @returns PersonalLinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static createPersonalLinkTemplateApiV1PersonalLinkTemplatesPost({
        requestBody,
    }: {
        requestBody: PersonalLinkTemplateCreate,
    }): CancelablePromise<PersonalLinkTemplateRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/personal-link-templates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Export Personal Link Templates
     * Export selected current-user personal link templates as a portable JSON bundle.
     * @returns LinkTemplateExportBundle Successful Response
     * @throws ApiError
     */
    public static exportPersonalLinkTemplatesApiV1PersonalLinkTemplatesExportPost({
        requestBody,
    }: {
        requestBody: LinkTemplateExportRequest,
    }): CancelablePromise<LinkTemplateExportBundle> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/personal-link-templates/export',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Import Personal Link Templates
     * Import current-user personal templates from a portable single-template or bundle payload.
     * @returns PersonalLinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static importPersonalLinkTemplatesApiV1PersonalLinkTemplatesImportPost({
        requestBody,
    }: {
        requestBody: any,
    }): CancelablePromise<Array<PersonalLinkTemplateRead>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/personal-link-templates/import',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Personal Link Template
     * Get one current-user personal link template.
     * @returns PersonalLinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static getPersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdGet({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<PersonalLinkTemplateRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/personal-link-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Personal Link Template
     * Update a current-user personal link template.
     * @returns PersonalLinkTemplateRead Successful Response
     * @throws ApiError
     */
    public static updatePersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdPatch({
        templateId,
        requestBody,
    }: {
        templateId: number,
        requestBody: PersonalLinkTemplateUpdate,
    }): CancelablePromise<PersonalLinkTemplateRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/personal-link-templates/{template_id}',
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
     * Delete Personal Link Template
     * Delete a current-user personal link template.
     * @returns void
     * @throws ApiError
     */
    public static deletePersonalLinkTemplateApiV1PersonalLinkTemplatesTemplateIdDelete({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/personal-link-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
