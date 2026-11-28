/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardRecord } from './DashboardRecord';
export type DashboardRecords = {
    entity: 'alerts' | 'cases' | 'tasks';
    columns: Array<string>;
    items: Array<DashboardRecord>;
    total: number;
    page: number;
    page_size: number;
    evaluated_at: string;
    original_count?: (number | null);
    queue_statuses?: (Array<string> | null);
};

