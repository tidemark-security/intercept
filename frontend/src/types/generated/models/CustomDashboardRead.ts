/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardDefinition } from './DashboardDefinition';
export type CustomDashboardRead = {
    id: string;
    title: string;
    scope: 'starter' | 'personal' | 'organization';
    revision: number;
    can_edit: boolean;
    definition: DashboardDefinition;
};

