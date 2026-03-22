/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Rejection breakdown by category.
 */
export type AITriageByCategory = {
    /**
     * Rejection category (null for uncategorized)
     */
    category?: (string | null);
    /**
     * Number of rejections in this category
     */
    count?: number;
    /**
     * Percentage of total rejections
     */
    percentage?: (number | null);
};

