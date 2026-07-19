/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request to generate presigned upload URL.
 */
export type PresignedUploadRequest = {
    /**
     * Original filename
     */
    filename: string;
    /**
     * File size in bytes
     */
    file_size: number;
    /**
     * Client-reported MIME type (validated server-side)
     */
    mime_type: string;
    /**
     * Free text description to store with the attachment
     */
    description?: (string | null);
    /**
     * Timestamp when the attachment was created or collected
     */
    timestamp?: (string | null);
    /**
     * Tags to store with the attachment
     */
    tags?: (Array<string> | null);
};

