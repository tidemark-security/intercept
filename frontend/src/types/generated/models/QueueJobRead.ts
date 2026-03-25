/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Read-only schema for a pgqueuer job (active or logged).
 */
export type QueueJobRead = {
    id: number;
    entrypoint: string;
    status: string;
    priority: number;
    payload?: (Record<string, any> | null);
    created?: (string | null);
    updated?: (string | null);
    picked_at?: (string | null);
    finished_at?: (string | null);
    duration_ms?: (number | null);
    traceback?: (string | null);
};

