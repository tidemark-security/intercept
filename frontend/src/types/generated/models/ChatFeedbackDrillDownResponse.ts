/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ChatFeedbackMessageDetail } from './ChatFeedbackMessageDetail';
/**
 * Paginated response for chat feedback drill-down.
 */
export type ChatFeedbackDrillDownResponse = {
    items?: Array<ChatFeedbackMessageDetail>;
    /**
     * Total count matching filters
     */
    total?: number;
    limit?: number;
    offset?: number;
};

