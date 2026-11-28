/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardFilter } from './DashboardFilter';
import type { DashboardLayout } from './DashboardLayout';
import type { DashboardTable } from './DashboardTable';
import type { DashboardWidgetParameters } from './DashboardWidgetParameters';
export type DashboardWidget = {
    id: string;
    title: string;
    measure: string;
    display: 'number' | 'trend' | 'breakdown' | 'table';
    group_by?: (string | null);
    aggregation?: ('mean' | 'p50' | 'p95' | null);
    filters?: Array<DashboardFilter>;
    parameters?: DashboardWidgetParameters;
    layout: DashboardLayout;
    table?: (DashboardTable | null);
};

