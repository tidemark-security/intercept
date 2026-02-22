/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DateRangeApplied } from './DateRangeApplied';
import type { EntityType } from './EntityType';
import type { SearchResultItem } from './SearchResultItem';
/**
 * API response for paginated search (supports multiple entity types).
 */
export type PaginatedSearchResponse = {
    /**
     * Search results sorted by score
     */
    results?: Array<SearchResultItem>;
    /**
     * Total number of matching results
     */
    total: number;
    /**
     * Number of results skipped (offset)
     */
    skip: number;
    /**
     * Maximum number of results returned
     */
    limit: number;
    /**
     * The search query that was executed
     */
    query: string;
    /**
     * The entity types that were searched
     */
    entity_types: Array<EntityType>;
    /**
     * The date range that was applied
     */
    date_range: DateRangeApplied;
};

