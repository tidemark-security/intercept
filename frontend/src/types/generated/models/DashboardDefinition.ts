/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardDate } from './DashboardDate';
import type { DashboardParameters } from './DashboardParameters';
import type { DashboardWidget } from './DashboardWidget';
export type DashboardDefinition = {
    schema_version?: number;
    date?: DashboardDate;
    parameters?: DashboardParameters;
    widgets?: Array<DashboardWidget>;
};

