/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Priority } from './Priority';
import type { TaskStatus } from './TaskStatus';
/**
 * Schema for reading a task.
 */
export type TaskRead = {
    title: string;
    description?: (string | null);
    priority?: Priority;
    due_date?: (string | null);
    id: number;
    status: TaskStatus;
    assignee?: (string | null);
    created_by: string;
    case_id?: (number | null);
    linked_at?: (string | null);
    created_at: string;
    updated_at: string;
    timeline_items?: null;
    tags?: (Array<string> | null);
    readonly human_id: string;
};

