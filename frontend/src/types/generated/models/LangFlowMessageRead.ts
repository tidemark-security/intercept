/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageFeedback } from './MessageFeedback';
import type { MessageRole } from './MessageRole';
/**
 * Schema for reading a message.
 */
export type LangFlowMessageRead = {
    /**
     * Message author role
     */
    role: MessageRole;
    /**
     * Message text content
     */
    content: string;
    /**
     * Additional message context (tokens, model, etc.)
     */
    message_metadata?: Record<string, any>;
    id: string;
    session_id: string;
    created_at: string;
    feedback?: (MessageFeedback | null);
};

