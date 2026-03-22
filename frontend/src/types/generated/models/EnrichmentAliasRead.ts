/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for reading enrichment aliases.
 */
export type EnrichmentAliasRead = {
    provider_id: string;
    entity_type: string;
    canonical_value: string;
    canonical_display?: (string | null);
    alias_type: string;
    alias_value: string;
    attributes?: Record<string, any>;
    id: number;
    created_at: string;
    updated_at: string;
};

