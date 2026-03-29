/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request to stream a chat message response.
 */
export type StreamChatRequest = {
    /**
     * Message content
     */
    message: string;
    /**
     * Additional context
     */
    context?: (Record<string, any> | null);
};

