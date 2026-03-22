/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EntityType } from './EntityType';
/**
 * Single search result item.
 */
export type SearchResultItem = {
    /**
     * Type of entity (alert, case, task)
     */
    entity_type: EntityType;
    /**
     * Numeric ID of the entity
     */
    entity_id: number;
    /**
     * Human-readable ID (ALT-0000123, CAS-0000045, TSK-0000007)
     */
    human_id: string;
    /**
     * Entity title
     */
    title: string;
    /**
     * Matched text excerpt with <mark> tags around matches (max 150 chars)
     */
    snippet: string;
    /**
     * Relevance score (higher is more relevant)
     */
    score: number;
    /**
     * ID of timeline item if match was in timeline content
     */
    timeline_item_id?: (string | null);
    /**
     * When the entity was created
     */
    created_at: string;
    /**
     * Top-level entity tags
     */
    tags?: Array<string>;
};

