/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response-only tombstone for deleted timeline items.
 */
export type DeletedItem = {
    id: string;
    type?: string;
    deleted_at: string;
    deleted_by: string;
    original_type: string;
    original_created_at?: (string | null);
    original_created_by?: (string | null);
    parent_id?: (string | null);
    replies?: null;
};

