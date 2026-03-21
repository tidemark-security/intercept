/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Effective attachment upload and preview limits.
 */
export type AttachmentLimitsRead = {
    /**
     * Maximum attachment upload size in megabytes
     */
    max_upload_size_mb: number;
    /**
     * Maximum attachment upload size in bytes
     */
    max_upload_size_bytes: number;
    /**
     * Maximum image attachment preview size in megabytes
     */
    max_image_preview_size_mb: number;
    /**
     * Maximum image attachment preview size in bytes
     */
    max_image_preview_size_bytes: number;
    /**
     * Maximum text attachment preview size in megabytes
     */
    max_text_preview_size_mb: number;
    /**
     * Maximum text attachment preview size in bytes
     */
    max_text_preview_size_bytes: number;
};

