/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Summary statistics for AI chat feedback.
 */
export type AIChatMetricsSummary = {
    /**
     * Total AI assistant messages in period
     */
    total_messages?: number;
    /**
     * Messages with any feedback
     */
    total_with_feedback?: number;
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

