/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Runtime status for a registered enrichment provider.
 */
export type EnrichmentProviderStatusRead = {
    provider_id: string;
    display_name: string;
    settings_prefix: string;
    enabled: boolean;
    supports_bulk_sync: boolean;
    item_types?: Array<string>;
    cache_entry_count?: number;
    alias_count?: number;
    last_activity_at?: (string | null);
};

