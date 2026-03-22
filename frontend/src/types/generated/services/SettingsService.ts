/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AttachmentLimitsRead } from '../models/AttachmentLimitsRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SettingsService {
    /**
     * Get Attachment Limits Settings
     * Get effective attachment upload and preview limits for authenticated users.
     * @returns AttachmentLimitsRead Successful Response
     * @throws ApiError
     */
    public static getAttachmentLimitsSettingsApiV1SettingsAttachmentLimitsGet(): CancelablePromise<AttachmentLimitsRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/settings/attachment-limits',
        });
    }
}
