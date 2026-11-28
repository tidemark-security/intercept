/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardDefinition } from './DashboardDefinition';
export type DashboardUpdate = {
    title: string;
    definition: DashboardDefinition;
    scope?: 'personal' | 'organization';
    revision: number;
};

