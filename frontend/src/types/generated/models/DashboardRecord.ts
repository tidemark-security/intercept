/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardRecord = {
    id: number;
    human_id: string;
    title: string;
    created_at: string;
    status: string;
    priority: string;
    assignee?: (string | null);
    source?: (string | null);
    case_id?: (number | null);
    due_date?: (string | null);
    completed_at?: (string | null);
    elapsed_seconds?: (number | null);
    target_seconds?: (number | null);
};

