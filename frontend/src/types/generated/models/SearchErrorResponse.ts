/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Error response for search API.
 */
export type SearchErrorResponse = {
    /**
     * Human-readable error message
     */
    error: string;
    /**
     * Error code (INVALID_QUERY, INVALID_DATE_RANGE, INVALID_ENTITY_TYPE, UNAUTHORIZED, SEARCH_ERROR)
     */
    code: string;
    /**
     * Additional error details
     */
    detail?: (string | null);
};

