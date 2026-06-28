/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Tag match metadata explaining why a tag-filtered result matched.
 */
export type SearchTagMatch = {
    /**
     * Where the matching tag was found: entity or timeline
     */
    source: string;
    /**
     * The matched tag value
     */
    tag: string;
    /**
     * The filter value that matched the tag
     */
    filter: string;
    /**
     * Timeline item ID for timeline tag matches
     */
    timeline_item_id?: (string | null);
    /**
     * Timeline item type for timeline tag matches
     */
    timeline_item_type?: (string | null);
    /**
     * Short label for the matching timeline item
     */
    timeline_item_label?: (string | null);
};

