/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AcceptRecommendationRequest } from '../models/AcceptRecommendationRequest';
import type { AcceptRecommendationResponse } from '../models/AcceptRecommendationResponse';
import type { AlertCreate } from '../models/AlertCreate';
import type { AlertRead } from '../models/AlertRead';
import type { AlertReadWithCase } from '../models/AlertReadWithCase';
import type { AlertStatus } from '../models/AlertStatus';
import type { AlertTriageRequest } from '../models/AlertTriageRequest';
import type { AlertUpdate } from '../models/AlertUpdate';
import type { AttachmentStatusUpdate } from '../models/AttachmentStatusUpdate';
import type { Page_AlertRead_ } from '../models/Page_AlertRead_';
import type { PresignedDownloadResponse } from '../models/PresignedDownloadResponse';
import type { PresignedUploadRequest } from '../models/PresignedUploadRequest';
import type { PresignedUploadResponse } from '../models/PresignedUploadResponse';
import type { Priority } from '../models/Priority';
import type { RejectRecommendationRequest } from '../models/RejectRecommendationRequest';
import type { TriageRecommendationRead } from '../models/TriageRecommendationRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AlertsService {
    /**
     * Create Alert
     * Create a new alert.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static createAlertApiV1AlertsPost({
        requestBody,
    }: {
        requestBody: AlertCreate,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Alerts
     * Get alerts with comprehensive filtering and cursor pagination.
     *
     * Date filtering expects UTC ISO8601 strings with 'Z' suffix (e.g., "2025-10-20T14:30:00Z").
     * Alerts are filtered by created_at timestamp.
     * Search parameter matches against alert ID, title, or description using case-insensitive partial matching.
     * @returns Page_AlertRead_ Successful Response
     * @throws ApiError
     */
    public static getAlertsApiV1AlertsGet({
        status,
        assignee,
        caseId,
        priority,
        source,
        hasCase,
        startDate,
        endDate,
        search,
        sortBy = 'created_at',
        sortOrder = 'desc',
        page = 1,
        size = 50,
    }: {
        /**
         * Filter by multiple alert statuses
         */
        status?: (Array<AlertStatus> | null),
        /**
         * Filter by multiple assignee usernames
         */
        assignee?: (Array<string> | null),
        caseId?: (number | null),
        /**
         * Filter by multiple priorities
         */
        priority?: (Array<Priority> | null),
        source?: (string | null),
        hasCase?: (boolean | null),
        /**
         * Filter alerts created after this UTC datetime (ISO8601 format with 'Z' suffix)
         */
        startDate?: (string | null),
        /**
         * Filter alerts created before this UTC datetime (ISO8601 format with 'Z' suffix)
         */
        endDate?: (string | null),
        /**
         * Search alerts by ID, title, or description (case-insensitive partial match)
         */
        search?: (string | null),
        /**
         * Field to sort by
         */
        sortBy?: string,
        /**
         * Sort order
         */
        sortOrder?: string,
        /**
         * Page number
         */
        page?: number,
        /**
         * Page size
         */
        size?: number,
    }): CancelablePromise<Page_AlertRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/alerts',
            query: {
                'status': status,
                'assignee': assignee,
                'case_id': caseId,
                'priority': priority,
                'source': source,
                'has_case': hasCase,
                'start_date': startDate,
                'end_date': endDate,
                'search': search,
                'sort_by': sortBy,
                'sort_order': sortOrder,
                'page': page,
                'size': size,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Alert
     * Get a specific alert with case relationship.
     *
     * When include_linked_timelines=true, case and task timeline items will include
     * a source_timeline_items field containing the timeline from the linked entity.
     * @returns AlertReadWithCase Successful Response
     * @throws ApiError
     */
    public static getAlertApiV1AlertsAlertIdGet({
        alertId,
        includeLinkedTimelines = false,
    }: {
        alertId: number,
        /**
         * Include timeline items from linked cases and tasks as nested source_timeline_items
         */
        includeLinkedTimelines?: boolean,
    }): CancelablePromise<AlertReadWithCase> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/alerts/{alert_id}',
            path: {
                'alert_id': alertId,
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
     * Update Alert
     * Update an alert.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static updateAlertApiV1AlertsAlertIdPut({
        alertId,
        requestBody,
    }: {
        alertId: number,
        requestBody: AlertUpdate,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/alerts/{alert_id}',
            path: {
                'alert_id': alertId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Triage Alert
     * Triage an alert and optionally escalate to case.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static triageAlertApiV1AlertsAlertIdTriagePost({
        alertId,
        requestBody,
    }: {
        alertId: number,
        requestBody: AlertTriageRequest,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/triage',
            path: {
                'alert_id': alertId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Link Alert To Case
     * Link an alert to an existing case.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static linkAlertToCaseApiV1AlertsAlertIdLinkCaseCaseIdPost({
        alertId,
        caseId,
    }: {
        alertId: number,
        caseId: number,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/link-case/{case_id}',
            path: {
                'alert_id': alertId,
                'case_id': caseId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Unlink Alert From Case
     * Unlink an alert from its associated case.
     *
     * This will remove the case association and change the status from ESCALATED back to IN_PROGRESS.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static unlinkAlertFromCaseApiV1AlertsAlertIdUnlinkCasePost({
        alertId,
    }: {
        alertId: number,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/unlink-case',
            path: {
                'alert_id': alertId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Add Timeline Item
     * Add a timeline item to an alert.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static addTimelineItemApiV1AlertsAlertIdTimelinePost({
        alertId,
        requestBody,
    }: {
        alertId: number,
        requestBody: Record<string, any>,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/timeline',
            path: {
                'alert_id': alertId,
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
     * Update a specific timeline item in an alert.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static updateTimelineItemApiV1AlertsAlertIdTimelineItemIdPut({
        alertId,
        itemId,
        requestBody,
    }: {
        alertId: number,
        itemId: string,
        requestBody: Record<string, any>,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/alerts/{alert_id}/timeline/{item_id}',
            path: {
                'alert_id': alertId,
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
     * Remove a specific timeline item from an alert.
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static removeTimelineItemApiV1AlertsAlertIdTimelineItemIdDelete({
        alertId,
        itemId,
    }: {
        alertId: number,
        itemId: string,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/alerts/{alert_id}/timeline/{item_id}',
            path: {
                'alert_id': alertId,
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
    public static generateUploadUrlApiV1AlertsAlertIdTimelineAttachmentsUploadUrlPost({
        alertId,
        requestBody,
    }: {
        alertId: number,
        requestBody: PresignedUploadRequest,
    }): CancelablePromise<PresignedUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/timeline/attachments/upload-url',
            path: {
                'alert_id': alertId,
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
     * 4. Returns the updated alert
     * @returns AlertRead Successful Response
     * @throws ApiError
     */
    public static updateAttachmentStatusApiV1AlertsAlertIdTimelineItemsItemIdStatusPatch({
        alertId,
        itemId,
        requestBody,
    }: {
        alertId: number,
        itemId: string,
        requestBody: AttachmentStatusUpdate,
    }): CancelablePromise<AlertRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/alerts/{alert_id}/timeline/items/{item_id}/status',
            path: {
                'alert_id': alertId,
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
    public static generateDownloadUrlApiV1AlertsAlertIdTimelineItemsItemIdDownloadUrlGet({
        alertId,
        itemId,
    }: {
        alertId: number,
        itemId: string,
    }): CancelablePromise<PresignedDownloadResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/alerts/{alert_id}/timeline/items/{item_id}/download-url',
            path: {
                'alert_id': alertId,
                'item_id': itemId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Triage Recommendation
     * Get the current triage recommendation for an alert.
     *
     * Returns None if no recommendation exists.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getTriageRecommendationApiV1AlertsAlertIdTriageRecommendationGet({
        alertId,
    }: {
        alertId: number,
    }): CancelablePromise<(TriageRecommendationRead | null)> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/alerts/{alert_id}/triage-recommendation',
            path: {
                'alert_id': alertId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Enqueue Triage Recommendation
     * Enqueue AI triage for an alert.
     *
     * Creates a QUEUED placeholder recommendation and submits the triage job to the worker queue.
     * If a QUEUED or FAILED recommendation already exists, it will be updated in-place.
     * If a PENDING/ACCEPTED/REJECTED/SUPERSEDED recommendation exists, it will be superseded.
     *
     * Returns 400 if AI triage is not enabled (langflow.alert_triage_flow_id not configured).
     * @returns TriageRecommendationRead Successful Response
     * @throws ApiError
     */
    public static enqueueTriageRecommendationApiV1AlertsAlertIdTriageRecommendationEnqueuePost({
        alertId,
    }: {
        alertId: number,
    }): CancelablePromise<TriageRecommendationRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/triage-recommendation/enqueue',
            path: {
                'alert_id': alertId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Accept Triage Recommendation
     * Accept a triage recommendation and apply selected changes.
     *
     * By default, all suggested changes are applied. Use the request body
     * to selectively disable specific changes.
     *
     * If request_escalate_to_case is true on the recommendation:
     * - A new case is created from the alert
     * - The alert is linked and set to ESCALATED status
     * - Tasks are created from recommended_actions with case priority
     *
     * Returns the updated recommendation and case info if escalated.
     * @returns AcceptRecommendationResponse Successful Response
     * @throws ApiError
     */
    public static acceptTriageRecommendationApiV1AlertsAlertIdTriageRecommendationAcceptPost({
        alertId,
        requestBody,
    }: {
        alertId: number,
        requestBody: AcceptRecommendationRequest,
    }): CancelablePromise<AcceptRecommendationResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/triage-recommendation/accept',
            path: {
                'alert_id': alertId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Reject Triage Recommendation
     * Reject a triage recommendation with a category and optional reason.
     *
     * The rejection category is required. Additional details are optional
     * unless the category is OTHER, in which case a reason should be provided.
     * @returns TriageRecommendationRead Successful Response
     * @throws ApiError
     */
    public static rejectTriageRecommendationApiV1AlertsAlertIdTriageRecommendationRejectPost({
        alertId,
        requestBody,
    }: {
        alertId: number,
        requestBody: RejectRecommendationRequest,
    }): CancelablePromise<TriageRecommendationRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/alerts/{alert_id}/triage-recommendation/reject',
            path: {
                'alert_id': alertId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
