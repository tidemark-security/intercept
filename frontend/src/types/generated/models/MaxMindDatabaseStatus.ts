/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Current worker/storage status for a configured MaxMind database.
 */
export type MaxMindDatabaseStatus = {
    edition_id: string;
    available_in_storage?: boolean;
    loaded?: boolean;
    local_path?: (string | null);
    file_size_bytes?: (number | null);
    last_updated?: (string | null);
    content_sha256?: (string | null);
};

