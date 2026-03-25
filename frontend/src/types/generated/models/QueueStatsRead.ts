/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Aggregate count of active jobs grouped by entrypoint and status.
 */
export type QueueStatsRead = {
    entrypoint: string;
    status: string;
    count: number;
};

