/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for creating a session. context_type determines which flow to use from server settings.
 */
export type LangFlowSessionCreate = {
    /**
     * Context type (general, case, task, alert) - determines which flow to use
     */
    context_type?: (string | null);
    /**
     * Session title (auto-generated from first message if not provided)
     */
    title?: (string | null);
    /**
     * Conversation context/history
     */
    context?: Record<string, any>;
};

