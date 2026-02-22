/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response with presigned download URL.
 */
export type PresignedDownloadResponse = {
    /**
     * Presigned GET URL for direct download from storage
     */
    download_url: string;
    /**
     * Original filename for download
     */
    filename: string;
    /**
     * MIME type for Content-Type header
     */
    mime_type: string;
    /**
     * File size in bytes
     */
    file_size: number;
    /**
     * URL expiration timestamp
     */
    expires_at: string;
};

