/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UploadStatus } from './UploadStatus';
/**
 * Update attachment upload status.
 */
export type AttachmentStatusUpdate = {
    /**
     * New upload status
     */
    status: UploadStatus;
    /**
     * SHA256 hash of uploaded file (for verification)
     */
    file_hash?: (string | null);
};

