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
    mime_type?: (string | null);
};

