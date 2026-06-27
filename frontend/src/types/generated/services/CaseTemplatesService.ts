/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseTemplateApplyRequest } from '../models/CaseTemplateApplyRequest';
import type { CaseTemplateApplyResponse } from '../models/CaseTemplateApplyResponse';
import type { CaseTemplateCreate } from '../models/CaseTemplateCreate';
import type { CaseTemplateRead } from '../models/CaseTemplateRead';
import type { CaseTemplateStatus } from '../models/CaseTemplateStatus';
import type { CaseTemplateUpdate } from '../models/CaseTemplateUpdate';
import type { Page_CaseTemplateRead_ } from '../models/Page_CaseTemplateRead_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class CaseTemplatesService {
    /**
     * List Case Templates
     * @returns Page_CaseTemplateRead_ Successful Response
     * @throws ApiError
     */
    public static listCaseTemplatesApiV1CaseTemplatesGet({
        status,
        search,
        page = 1,
        size = 50,
    }: {
        /**
         * Template lifecycle statuses to include
         */
        status?: (Array<CaseTemplateStatus> | null),
        /**
         * Search title, description, and Template Task text
         */
        search?: (string | null),
        /**
         * Page number
         */
        page?: number,
        /**
         * Page size
         */
        size?: number,
    }): CancelablePromise<Page_CaseTemplateRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/case-templates',
            query: {
                'status': status,
                'search': search,
                'page': page,
                'size': size,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Case Template
     * @returns CaseTemplateRead Successful Response
     * @throws ApiError
     */
    public static createCaseTemplateApiV1CaseTemplatesPost({
        requestBody,
    }: {
        requestBody: CaseTemplateCreate,
    }): CancelablePromise<CaseTemplateRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-templates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Case Template
     * @returns CaseTemplateRead Successful Response
     * @throws ApiError
     */
    public static getCaseTemplateApiV1CaseTemplatesTemplateIdGet({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<CaseTemplateRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/case-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Case Template
     * @returns CaseTemplateRead Successful Response
     * @throws ApiError
     */
    public static updateCaseTemplateApiV1CaseTemplatesTemplateIdPut({
        templateId,
        requestBody,
    }: {
        templateId: number,
        requestBody: CaseTemplateUpdate,
    }): CancelablePromise<CaseTemplateRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/case-templates/{template_id}',
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
     * Delete Case Template
     * @returns CaseTemplateRead Successful Response
     * @throws ApiError
     */
    public static deleteCaseTemplateApiV1CaseTemplatesTemplateIdDelete({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<CaseTemplateRead> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/case-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Publish Case Template
     * @returns CaseTemplateRead Successful Response
     * @throws ApiError
     */
    public static publishCaseTemplateApiV1CaseTemplatesTemplateIdPublishPost({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<CaseTemplateRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-templates/{template_id}/publish',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Disable Case Template
     * @returns CaseTemplateRead Successful Response
     * @throws ApiError
     */
    public static disableCaseTemplateApiV1CaseTemplatesTemplateIdDisablePost({
        templateId,
    }: {
        templateId: number,
    }): CancelablePromise<CaseTemplateRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-templates/{template_id}/disable',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Case Template
     * @returns CaseTemplateApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyCaseTemplateApiV1CaseTemplatesCasesCaseIdApplyTemplateIdPost({
        caseId,
        templateId,
        requestBody,
    }: {
        caseId: number,
        templateId: number,
        requestBody: CaseTemplateApplyRequest,
    }): CancelablePromise<CaseTemplateApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-templates/cases/{case_id}/apply/{template_id}',
            path: {
                'case_id': caseId,
                'template_id': templateId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
