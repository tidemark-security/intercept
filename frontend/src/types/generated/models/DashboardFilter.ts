/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardFilter = {
    field: 'priority' | 'status' | 'assignee' | 'source' | 'title' | 'tags' | 'picerl_stage';
    op: 'in' | 'contains_all' | 'excludes_all';
    value: Array<string>;
};

