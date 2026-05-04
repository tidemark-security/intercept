/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AttachmentStatusUpdate } from '../models/AttachmentStatusUpdate';
import type { Page_TaskRead_ } from '../models/Page_TaskRead_';
import type { PresignedDownloadResponse } from '../models/PresignedDownloadResponse';
import type { PresignedUploadRequest } from '../models/PresignedUploadRequest';
import type { PresignedUploadResponse } from '../models/PresignedUploadResponse';
import type { TaskCreate } from '../models/TaskCreate';
import type { TaskRead } from '../models/TaskRead';
import type { TaskStatus } from '../models/TaskStatus';
import type { TaskUpdate } from '../models/TaskUpdate';
import type { TimelineGraphPatch } from '../models/TimelineGraphPatch';
import type { TimelineGraphRead } from '../models/TimelineGraphRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class TasksService {
    /**
     * Create Task
     * Create a new task.
     *
     * If no assignee is specified, the task will be assigned to the creator (per spec requirement).
     * Tasks can optionally be linked to a case via case_id.
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static createTaskApiV1TasksPost({
        requestBody,
    }: {
        requestBody: TaskCreate,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/tasks',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Tasks
     * Get tasks with optional filtering and pagination.
     *
     * Returns a paginated response with items, total count, page information.
     * Search parameter matches against task title or description using case-insensitive partial matching.
     * Date filtering expects UTC ISO8601 strings with 'Z' suffix (e.g., "2025-10-20T14:30:00Z").
     * Tasks are filtered by created_at timestamp.
     * @returns Page_TaskRead_ Successful Response
     * @throws ApiError
     */
    public static getTasksApiV1TasksGet({
        skip,
        limit = 100,
        status,
        assignee,
        caseId,
        search,
        startDate,
        endDate,
        page = 1,
        size = 50,
    }: {
        skip?: number,
        limit?: number,
        /**
         * Filter by multiple task statuses
         */
        status?: (Array<TaskStatus> | null),
        assignee?: (string | null),
        /**
         * Filter by case ID
         */
        caseId?: (number | null),
        /**
         * Search tasks by title or description (case-insensitive partial match)
         */
        search?: (string | null),
        /**
         * Filter tasks created after this UTC datetime (ISO8601 format with 'Z' suffix)
         */
        startDate?: (string | null),
        /**
         * Filter tasks created before this UTC datetime (ISO8601 format with 'Z' suffix)
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
    }): CancelablePromise<Page_TaskRead_> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/tasks',
            query: {
                'skip': skip,
                'limit': limit,
                'status': status,
                'assignee': assignee,
                'case_id': caseId,
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
     * Get Task
     * Get a specific task by ID or human ID (TSK-0000001).
     *
     * When include_linked_timelines=true, case and alert timeline items will include
     * a source_timeline_items field containing the timeline from the linked entity.
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static getTaskApiV1TasksTaskIdGet({
        taskId,
        includeLinkedTimelines = false,
    }: {
        taskId: number,
        /**
         * Include timeline items from linked cases and alerts as nested source_timeline_items
         */
        includeLinkedTimelines?: boolean,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/tasks/{task_id}',
            path: {
                'task_id': taskId,
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
     * Update Task
     * Update a task.
     *
     * The updated_at timestamp is automatically refreshed on any update (per spec requirement).
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static updateTaskApiV1TasksTaskIdPut({
        taskId,
        requestBody,
    }: {
        taskId: number,
        requestBody: TaskUpdate,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/tasks/{task_id}',
            path: {
                'task_id': taskId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Task
     * Delete a task.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteTaskApiV1TasksTaskIdDelete({
        taskId,
    }: {
        taskId: number,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/tasks/{task_id}',
            path: {
                'task_id': taskId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Timeline Graph
     * Get the shared timeline graph document for a task.
     * @returns TimelineGraphRead Successful Response
     * @throws ApiError
     */
    public static getTimelineGraphApiV1TasksTaskIdTimelineGraphGet({
        taskId,
    }: {
        taskId: number,
    }): CancelablePromise<TimelineGraphRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/tasks/{task_id}/timeline-graph',
            path: {
                'task_id': taskId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Timeline Graph
     * Patch the shared timeline graph document for a task.
     * @returns TimelineGraphRead Successful Response
     * @throws ApiError
     */
    public static patchTimelineGraphApiV1TasksTaskIdTimelineGraphPatch({
        taskId,
        requestBody,
    }: {
        taskId: number,
        requestBody: TimelineGraphPatch,
    }): CancelablePromise<TimelineGraphRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/tasks/{task_id}/timeline-graph',
            path: {
                'task_id': taskId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Add Timeline Item
     * Add a timeline item to a task.
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static addTimelineItemApiV1TasksTaskIdTimelinePost({
        taskId,
        requestBody,
    }: {
        taskId: number,
        requestBody: Record<string, any>,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/tasks/{task_id}/timeline',
            path: {
                'task_id': taskId,
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
     * Update a specific timeline item in a task.
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static updateTimelineItemApiV1TasksTaskIdTimelineItemIdPut({
        taskId,
        itemId,
        requestBody,
    }: {
        taskId: number,
        itemId: string,
        requestBody: Record<string, any>,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/tasks/{task_id}/timeline/{item_id}',
            path: {
                'task_id': taskId,
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
     * Remove a specific timeline item from a task.
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static removeTimelineItemApiV1TasksTaskIdTimelineItemIdDelete({
        taskId,
        itemId,
    }: {
        taskId: number,
        itemId: string,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/tasks/{task_id}/timeline/{item_id}',
            path: {
                'task_id': taskId,
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
     * @returns PresignedUploadResponse Successful Response
     * @throws ApiError
     */
    public static generateUploadUrlApiV1TasksTaskIdTimelineAttachmentsUploadUrlPost({
        taskId,
        requestBody,
    }: {
        taskId: number,
        requestBody: PresignedUploadRequest,
    }): CancelablePromise<PresignedUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/tasks/{task_id}/timeline/attachments/upload-url',
            path: {
                'task_id': taskId,
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
     * @returns TaskRead Successful Response
     * @throws ApiError
     */
    public static updateAttachmentStatusApiV1TasksTaskIdTimelineItemsItemIdStatusPatch({
        taskId,
        itemId,
        requestBody,
    }: {
        taskId: number,
        itemId: string,
        requestBody: AttachmentStatusUpdate,
    }): CancelablePromise<TaskRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/tasks/{task_id}/timeline/items/{item_id}/status',
            path: {
                'task_id': taskId,
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
     * @returns PresignedDownloadResponse Successful Response
     * @throws ApiError
     */
    public static generateDownloadUrlApiV1TasksTaskIdTimelineItemsItemIdDownloadUrlGet({
        taskId,
        itemId,
        download = false,
    }: {
        taskId: number,
        itemId: string,
        /**
         * Generate a forced-download URL
         */
        download?: boolean,
    }): CancelablePromise<PresignedDownloadResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/tasks/{task_id}/timeline/items/{item_id}/download-url',
            path: {
                'task_id': taskId,
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
}
