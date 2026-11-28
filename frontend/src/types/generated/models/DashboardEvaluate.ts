/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardDate } from './DashboardDate';
import type { DashboardDefinition } from './DashboardDefinition';
export type DashboardEvaluate = {
    definition: DashboardDefinition;
    date?: (DashboardDate | null);
    timezone?: string;
    dashboard_id?: (string | null);
    revision?: (number | null);
};

