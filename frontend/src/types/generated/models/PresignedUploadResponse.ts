/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response with presigned upload URL and metadata.
 */
export type PresignedUploadResponse = {
    /**
     * Timeline item ID created for this upload
     */
    item_id: string;
    /**
     * Presigned PUT URL for direct upload to storage
     */
    upload_url: string;
    /**
     * Object storage key for this file
     */
    storage_key: string;
    /**
     * URL expiration timestamp
     */
    expires_at: string;
    /**
     * Maximum allowed file size in bytes
     */
    max_file_size: number;
};

