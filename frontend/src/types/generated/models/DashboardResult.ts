/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardPoint } from './DashboardPoint';
import type { DashboardRecords } from './DashboardRecords';
export type DashboardResult = {
    widget_id: string;
    points?: Array<DashboardPoint>;
    records?: (DashboardRecords | null);
    truncated?: boolean;
    error?: (string | null);
};

