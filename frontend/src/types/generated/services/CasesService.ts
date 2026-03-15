/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AttachmentStatusUpdate } from '../models/AttachmentStatusUpdate';
import type { Body_bulk_update_cases_api_v1_cases_bulk_update_post } from '../models/Body_bulk_update_cases_api_v1_cases_bulk_update_post';
import type { CaseCreate } from '../models/CaseCreate';
import type { CaseRead } from '../models/CaseRead';
import type { CaseReadWithAlerts } from '../models/CaseReadWithAlerts';
import type { CaseStatus } from '../models/CaseStatus';
import type { CaseUpdate } from '../models/CaseUpdate';
import type { Page_CaseRead_ } from '../models/Page_CaseRead_';
import type { PresignedDownloadResponse } from '../models/PresignedDownloadResponse';
import type { PresignedUploadRequest } from '../models/PresignedUploadRequest';
import type { PresignedUploadResponse } from '../models/PresignedUploadResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class CasesService {
    /**
     * Create Case
     * Create a new case.
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static createCaseApiV1CasesPost({
        requestBody,
    }: {
        requestBody: CaseCreate,
    }): CancelablePromise<CaseRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/cases',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Cases
     * Get cases with optional filtering and pagination.
     *
     * Returns a paginated response with items, total count, page information.
     * Search parameter matches against case title or description using case-insensitive partial matching.
     * Date filtering expects UTC ISO8601 strings with 'Z' suffix (e.g., "2025-10-20T14:30:00Z").
     * Cases are filtered by created_at timestamp.
     * @returns Page_CaseRead_ Successful Response
     * @throws ApiError
     */
    public static getCasesApiV1CasesGet({
        skip,
        limit = 100,
        status,
        assignee,
        search,
        startDate,
        endDate,
        page = 1,
        size = 50,
    }: {
        skip?: number,
        limit?: number,
        /**
         * Filter by multiple case statuses
         */
        status?: (Array<CaseStatus> | null),
        assignee?: (string | null),
        /**
         * Search cases by title or description (case-insensitive partial match)
         */
        search?: (string | null),
        /**
         * Filter cases created after this UTC datetime (ISO8601 format with 'Z' suffix)
         */
        startDate?: (string | null),
        /**
         * Filter cases created before this UTC datetime (ISO8601 format with 'Z' suffix)
         */
        endDate?: (string | null),
        /**
         * Page number
         */
        page?: number,
        /**
         * Page size
         */
        size?: number,
    }): CancelablePromise<Page_CaseRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/cases',
            query: {
                'skip': skip,
                'limit': limit,
                'status': status,
                'assignee': assignee,
                'search': search,
                'start_date': startDate,
                'end_date': endDate,
                'page': page,
                'size': size,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Case
     * Get a specific case with alerts and audit logs.
     *
     * When include_linked_timelines=true, alert and task timeline items will include
     * a source_timeline_items field containing the timeline from the linked entity.
     * @returns CaseReadWithAlerts Successful Response
     * @throws ApiError
     */
    public static getCaseApiV1CasesCaseIdGet({
        caseId,
        includeLinkedTimelines = false,
    }: {
        caseId: number,
        /**
         * Include timeline items from linked alerts and tasks as nested source_timeline_items
         */
        includeLinkedTimelines?: boolean,
    }): CancelablePromise<CaseReadWithAlerts> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/cases/{case_id}',
            path: {
                'case_id': caseId,
            },
            query: {
                'include_linked_timelines': includeLinkedTimelines,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Case
     * Update a case.
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static updateCaseApiV1CasesCaseIdPut({
        caseId,
        requestBody,
    }: {
        caseId: number,
        requestBody: CaseUpdate,
    }): CancelablePromise<CaseRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/cases/{case_id}',
            path: {
                'case_id': caseId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Case
     * Delete a case.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteCaseApiV1CasesCaseIdDelete({
        caseId,
    }: {
        caseId: number,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/cases/{case_id}',
            path: {
                'case_id': caseId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Add Timeline Item
     * Add a timeline item to a case.
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static addTimelineItemApiV1CasesCaseIdTimelinePost({
        caseId,
        requestBody,
    }: {
        caseId: number,
        requestBody: Record<string, any>,
    }): CancelablePromise<CaseRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/cases/{case_id}/timeline',
            path: {
                'case_id': caseId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Timeline Item
     * Update a timeline item in a case.
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static updateTimelineItemApiV1CasesCaseIdTimelineItemIdPut({
        caseId,
        itemId,
        requestBody,
    }: {
        caseId: number,
        itemId: string,
        requestBody: Record<string, any>,
    }): CancelablePromise<CaseRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/cases/{case_id}/timeline/{item_id}',
            path: {
                'case_id': caseId,
                'item_id': itemId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Remove Timeline Item
     * Remove a timeline item from a case.
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static removeTimelineItemApiV1CasesCaseIdTimelineItemIdDelete({
        caseId,
        itemId,
    }: {
        caseId: number,
        itemId: string,
    }): CancelablePromise<CaseRead> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/cases/{case_id}/timeline/{item_id}',
            path: {
                'case_id': caseId,
                'item_id': itemId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Upload Url
     * Generate presigned upload URL and create timeline attachment item.
     *
     * This endpoint:
     * 1. Validates file size and type
     * 2. Creates an AttachmentItem with 'uploading' status
     * 3. Generates a presigned PUT URL for direct upload to storage
     * 4. Returns the URL and item metadata
     * @returns PresignedUploadResponse Successful Response
     * @throws ApiError
     */
    public static generateUploadUrlApiV1CasesCaseIdTimelineAttachmentsUploadUrlPost({
        caseId,
        requestBody,
    }: {
        caseId: number,
        requestBody: PresignedUploadRequest,
    }): CancelablePromise<PresignedUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/cases/{case_id}/timeline/attachments/upload-url',
            path: {
                'case_id': caseId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Attachment Status
     * Update attachment upload status.
     *
     * This endpoint:
     * 1. Verifies the timeline item exists and is an attachment
     * 2. If status is 'complete', verifies file exists in storage
     * 3. Updates the upload_status field
     * 4. Returns the updated case
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static updateAttachmentStatusApiV1CasesCaseIdTimelineItemsItemIdStatusPatch({
        caseId,
        itemId,
        requestBody,
    }: {
        caseId: number,
        itemId: string,
        requestBody: AttachmentStatusUpdate,
    }): CancelablePromise<CaseRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/cases/{case_id}/timeline/items/{item_id}/status',
            path: {
                'case_id': caseId,
                'item_id': itemId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Generate Download Url
     * Generate presigned download URL for an attachment.
     *
     * This endpoint:
     * 1. Verifies the timeline item exists and is an attachment
     * 2. Verifies upload is complete
     * 3. Generates a presigned GET URL for download
     * 4. Returns the URL and file metadata
     * @returns PresignedDownloadResponse Successful Response
     * @throws ApiError
     */
    public static generateDownloadUrlApiV1CasesCaseIdTimelineItemsItemIdDownloadUrlGet({
        caseId,
        itemId,
        download = false,
    }: {
        caseId: number,
        itemId: string,
        /**
         * Generate a forced-download URL
         */
        download?: boolean,
    }): CancelablePromise<PresignedDownloadResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/cases/{case_id}/timeline/items/{item_id}/download-url',
            path: {
                'case_id': caseId,
                'item_id': itemId,
            },
            query: {
                'download': download,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Bulk Update Cases
     * Bulk update multiple cases.
     * @returns CaseRead Successful Response
     * @throws ApiError
     */
    public static bulkUpdateCasesApiV1CasesBulkUpdatePost({
        requestBody,
    }: {
        requestBody: Body_bulk_update_cases_api_v1_cases_bulk_update_post,
    }): CancelablePromise<Array<CaseRead>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/cases/bulk-update',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
