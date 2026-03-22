/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request to send a chat message.
 */
export type ChatRequest = {
    /**
     * Session ID for the conversation
     */
    session_id: string;
    /**
     * Message content
     */
    content: string;
    /**
     * Additional context
     */
    context?: (Record<string, any> | null);
};

