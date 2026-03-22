/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SessionStatus } from './SessionStatus';
/**
 * Schema for reading a session.
 */
export type LangFlowSessionRead = {
    /**
     * LangFlow flow identifier
     */
    flow_id: string;
    /**
     * Session title (auto-generated from first message if not provided)
     */
    title?: (string | null);
    /**
     * Conversation context/history
     */
    context?: Record<string, any>;
    /**
     * Session status
     */
    status?: SessionStatus;
    id: string;
    user_id: string;
    created_at: string;
    updated_at: string;
    completed_at?: (string | null);
    message_count?: number;
};

