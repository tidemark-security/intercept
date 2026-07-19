/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseRunbookApplyRequest } from '../models/CaseRunbookApplyRequest';
import type { CaseRunbookApplyResponse } from '../models/CaseRunbookApplyResponse';
import type { CaseRunbookCreate } from '../models/CaseRunbookCreate';
import type { CaseRunbookRead } from '../models/CaseRunbookRead';
import type { CaseRunbookStatus } from '../models/CaseRunbookStatus';
import type { CaseRunbookUpdate } from '../models/CaseRunbookUpdate';
import type { Page_CaseRunbookRead_ } from '../models/Page_CaseRunbookRead_';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class CaseRunbooksService {
    /**
     * List Case Runbooks
     * @returns Page_CaseRunbookRead_ Successful Response
     * @throws ApiError
     */
    public static listCaseRunbooksApiV1CaseRunbooksGet({
        status,
        search,
        page = 1,
        size = 50,
    }: {
        /**
         * Runbook lifecycle statuses to include
         */
        status?: (Array<CaseRunbookStatus> | null),
        /**
         * Search title, description, and Runbook Task text
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
    }): CancelablePromise<Page_CaseRunbookRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/case-runbooks',
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
     * Create Case Runbook
     * @returns CaseRunbookRead Successful Response
     * @throws ApiError
     */
    public static createCaseRunbookApiV1CaseRunbooksPost({
        requestBody,
    }: {
        requestBody: CaseRunbookCreate,
    }): CancelablePromise<CaseRunbookRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-runbooks',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Case Runbook
     * @returns CaseRunbookRead Successful Response
     * @throws ApiError
     */
    public static getCaseRunbookApiV1CaseRunbooksRunbookIdGet({
        runbookId,
    }: {
        runbookId: number,
    }): CancelablePromise<CaseRunbookRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/case-runbooks/{runbook_id}',
            path: {
                'runbook_id': runbookId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Case Runbook
     * @returns CaseRunbookRead Successful Response
     * @throws ApiError
     */
    public static updateCaseRunbookApiV1CaseRunbooksRunbookIdPut({
        runbookId,
        requestBody,
    }: {
        runbookId: number,
        requestBody: CaseRunbookUpdate,
    }): CancelablePromise<CaseRunbookRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/case-runbooks/{runbook_id}',
            path: {
                'runbook_id': runbookId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Case Runbook
     * @returns CaseRunbookRead Successful Response
     * @throws ApiError
     */
    public static deleteCaseRunbookApiV1CaseRunbooksRunbookIdDelete({
        runbookId,
    }: {
        runbookId: number,
    }): CancelablePromise<CaseRunbookRead> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/case-runbooks/{runbook_id}',
            path: {
                'runbook_id': runbookId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Publish Case Runbook
     * @returns CaseRunbookRead Successful Response
     * @throws ApiError
     */
    public static publishCaseRunbookApiV1CaseRunbooksRunbookIdPublishPost({
        runbookId,
    }: {
        runbookId: number,
    }): CancelablePromise<CaseRunbookRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-runbooks/{runbook_id}/publish',
            path: {
                'runbook_id': runbookId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Disable Case Runbook
     * @returns CaseRunbookRead Successful Response
     * @throws ApiError
     */
    public static disableCaseRunbookApiV1CaseRunbooksRunbookIdDisablePost({
        runbookId,
    }: {
        runbookId: number,
    }): CancelablePromise<CaseRunbookRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-runbooks/{runbook_id}/disable',
            path: {
                'runbook_id': runbookId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Apply Case Runbook
     * @returns CaseRunbookApplyResponse Successful Response
     * @throws ApiError
     */
    public static applyCaseRunbookApiV1CaseRunbooksCasesCaseIdApplyRunbookIdPost({
        caseId,
        runbookId,
        requestBody,
    }: {
        caseId: number,
        runbookId: number,
        requestBody: CaseRunbookApplyRequest,
    }): CancelablePromise<CaseRunbookApplyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/case-runbooks/cases/{case_id}/apply/{runbook_id}',
            path: {
                'case_id': caseId,
                'runbook_id': runbookId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
