/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageFeedback } from './MessageFeedback';
/**
 * Chat message with feedback for drill-down reports.
 */
export type ChatFeedbackMessageDetail = {
    id: string;
    session_id: string;
    /**
     * Session title
     */
    session_title?: (string | null);
    /**
     * LangFlow flow ID
     */
    flow_id?: (string | null);
    user_id: string;
    /**
     * Username who received the message
     */
    username: string;
    /**
     * User display name
     */
    display_name?: (string | null);
    /**
     * Message content (truncated preview)
     */
    content: string;
    feedback: MessageFeedback;
    created_at: string;
};

