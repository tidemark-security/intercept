/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SavedFilterDateRange } from './SavedFilterDateRange';
export type SavedFilterSnapshot = {
    search?: string;
    status?: (Array<string> | null);
    assignee?: (Array<string> | null);
    include_tags?: (Array<string> | null);
    exclude_tags?: (Array<string> | null);
    date_range?: (SavedFilterDateRange | null);
    sort_by?: ('created_at' | 'updated_at' | 'priority' | 'status' | null);
    sort_order?: ('asc' | 'desc' | null);
};

