/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response after sending a chat message.
 */
export type ChatResponse = {
    /**
     * ID of the created message
     */
    message_id: string;
    /**
     * Session ID
     */
    session_id: string;
    /**
     * Processing status
     */
    status: string;
    /**
     * URL for streaming response
     */
    stream_url?: (string | null);
};

