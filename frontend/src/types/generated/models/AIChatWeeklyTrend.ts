/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Weekly trend data for AI chat feedback.
 */
export type AIChatWeeklyTrend = {
    /**
     * Start of the week (Monday)
     */
    week_start: string;
    /**
     * Total AI messages
     */
    total_messages?: number;
    /**
     * Positive feedback count
     */
    positive_feedback?: number;
    /**
     * Negative feedback count
     */
    negative_feedback?: number;
    /**
     * Percentage of messages with feedback
     */
    feedback_rate?: (number | null);
    /**
     * Positive / (Positive + Negative)
     */
    satisfaction_rate?: (number | null);
};

