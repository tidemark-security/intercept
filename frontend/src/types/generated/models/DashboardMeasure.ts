/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardFilterOption } from './DashboardFilterOption';
export type DashboardMeasure = {
    id: string;
    entity: 'alerts' | 'cases' | 'tasks';
    label: string;
    description: string;
    date_basis: 'created_at' | 'triaged_at' | 'closed_at' | 'current';
    unit: 'count' | 'seconds' | 'percent';
    displays: Array<'number' | 'trend' | 'breakdown' | 'table'>;
    dimensions: Array<string>;
    filters: Array<DashboardFilterOption>;
    parameters: Array<string>;
    aggregations: Array<'mean' | 'p50' | 'p95'>;
    record_columns: Array<string>;
};

