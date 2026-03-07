/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ChatRequest } from '../models/ChatRequest';
import type { ChatResponse } from '../models/ChatResponse';
import type { LangFlowMessageRead } from '../models/LangFlowMessageRead';
import type { LangFlowSessionCreate } from '../models/LangFlowSessionCreate';
import type { LangFlowSessionRead } from '../models/LangFlowSessionRead';
import type { LangFlowSessionUpdate } from '../models/LangFlowSessionUpdate';
import type { MessageFeedbackRequest } from '../models/MessageFeedbackRequest';
import type { TestConnectionResponse } from '../models/TestConnectionResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class LangflowService {
    /**
     * Create Session
     * Create a new LangFlow chat session.
     *
     * Requires authentication. Creates a session linked to the current user.
     * The flow_id is determined by the context_type from server settings.
     * @returns LangFlowSessionRead Successful Response
     * @throws ApiError
     */
    public static createSessionApiV1LangflowSessionsPost({
        requestBody,
    }: {
        requestBody: LangFlowSessionCreate,
    }): CancelablePromise<LangFlowSessionRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/langflow/sessions',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Sessions
     * List chat sessions for the current user by default.
     *
     * Requires authentication. Returns sessions in reverse chronological order (most recent first).
     * Supports pagination with skip and limit parameters. Admin users may provide
     * a username query parameter to list sessions for a specific user.
     * @returns LangFlowSessionRead Successful Response
     * @throws ApiError
     */
    public static listSessionsApiV1LangflowSessionsGet({
        skip,
        limit = 50,
        username,
    }: {
        skip?: number,
        limit?: number,
        username?: (string | null),
    }): CancelablePromise<Array<LangFlowSessionRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/langflow/sessions',
            query: {
                'skip': skip,
                'limit': limit,
                'username': username,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Session
     * Get a specific session for the current user by default.
     *
     * Requires authentication. Users can only access their own sessions.
     * Admin users may provide a username query parameter to get sessions for a specific user.
     * @returns LangFlowSessionRead Successful Response
     * @throws ApiError
     */
    public static getSessionApiV1LangflowSessionsSessionIdGet({
        sessionId,
        username,
    }: {
        sessionId: string,
        username?: (string | null),
    }): CancelablePromise<LangFlowSessionRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/langflow/sessions/{session_id}',
            path: {
                'session_id': sessionId,
            },
            query: {
                'username': username,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Session
     * Update a session (context or status).
     *
     * Requires authentication. Users can only update their own sessions.
     * @returns LangFlowSessionRead Successful Response
     * @throws ApiError
     */
    public static updateSessionApiV1LangflowSessionsSessionIdPatch({
        sessionId,
        requestBody,
    }: {
        sessionId: string,
        requestBody: LangFlowSessionUpdate,
    }): CancelablePromise<LangFlowSessionRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/langflow/sessions/{session_id}',
            path: {
                'session_id': sessionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Session
     * Delete a chat session and all its messages.
     *
     * Requires authentication. Users can only delete their own sessions.
     * @returns void
     * @throws ApiError
     */
    public static deleteSessionApiV1LangflowSessionsSessionIdDelete({
        sessionId,
    }: {
        sessionId: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/langflow/sessions/{session_id}',
            path: {
                'session_id': sessionId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Session Messages
     * Get all messages for a session.
     *
     * Requires authentication. Users can only access messages from their own sessions.
     * Returns messages in chronological order. Admin users may provide a username
     * query parameter to access messages for sessions belonging to a specific user.
     * @returns LangFlowMessageRead Successful Response
     * @throws ApiError
     */
    public static getSessionMessagesApiV1LangflowSessionsSessionIdMessagesGet({
        sessionId,
        username,
    }: {
        sessionId: string,
        username?: (string | null),
    }): CancelablePromise<Array<LangFlowMessageRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/langflow/sessions/{session_id}/messages',
            path: {
                'session_id': sessionId,
            },
            query: {
                'username': username,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Set Message Feedback
     * Set feedback on a chat message.
     *
     * Requires authentication. Users can only set feedback on messages from their own sessions.
     * @returns LangFlowMessageRead Successful Response
     * @throws ApiError
     */
    public static setMessageFeedbackApiV1LangflowMessagesMessageIdFeedbackPatch({
        messageId,
        requestBody,
    }: {
        messageId: string,
        requestBody: MessageFeedbackRequest,
    }): CancelablePromise<LangFlowMessageRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/langflow/messages/{message_id}/feedback',
            path: {
                'message_id': messageId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Clear Message Feedback
     * Clear feedback on a chat message.
     *
     * Requires authentication. Users can only clear feedback on messages from their own sessions.
     * @returns LangFlowMessageRead Successful Response
     * @throws ApiError
     */
    public static clearMessageFeedbackApiV1LangflowMessagesMessageIdFeedbackDelete({
        messageId,
    }: {
        messageId: string,
    }): CancelablePromise<LangFlowMessageRead> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/langflow/messages/{message_id}/feedback',
            path: {
                'message_id': messageId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Send Chat Message
     * Send a chat message to LangFlow.
     *
     * Requires authentication. Creates user message and sends to LangFlow.
     * Returns response with message ID and streaming URL.
     * @returns ChatResponse Successful Response
     * @throws ApiError
     */
    public static sendChatMessageApiV1LangflowChatPost({
        requestBody,
    }: {
        requestBody: ChatRequest,
    }): CancelablePromise<ChatResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/langflow/chat',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Test Langflow Connection
     * Test connection to LangFlow.
     *
     * Requires authentication. Useful for validating configuration.
     * @returns TestConnectionResponse Successful Response
     * @throws ApiError
     */
    public static testLangflowConnectionApiV1LangflowTestConnectionPost(): CancelablePromise<TestConnectionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/langflow/test-connection',
        });
    }
    /**
     * Stream Langflow Response
     * Stream LangFlow response via Server-Sent Events (SSE).
     *
     * Requires authentication. Users can only stream from their own sessions.
     *
     * This endpoint establishes an SSE connection and streams AI responses in real-time.
     * Use EventSource API on frontend to consume the stream.
     *
     * Query params:
     * - message: The message to send to LangFlow
     * @returns any Successful Response
     * @throws ApiError
     */
    public static streamLangflowResponseApiV1LangflowStreamSessionIdGet({
        sessionId,
        message,
    }: {
        sessionId: string,
        message: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/langflow/stream/{session_id}',
            path: {
                'session_id': sessionId,
            },
            query: {
                'message': message,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
