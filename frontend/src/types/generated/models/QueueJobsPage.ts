/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { QueueJobRead } from './QueueJobRead';
/**
 * Paginated response for queue jobs.
 */
export type QueueJobsPage = {
    items?: Array<QueueJobRead>;
    total?: number;
    page?: number;
    size?: number;
    pages?: number;
};

