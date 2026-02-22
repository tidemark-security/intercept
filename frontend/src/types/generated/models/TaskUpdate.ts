/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Priority } from './Priority';
import type { TaskStatus } from './TaskStatus';
/**
 * Schema for updating a task.
 */
export type TaskUpdate = {
    title?: (string | null);
    description?: (string | null);
    status?: (TaskStatus | null);
    priority?: (Priority | null);
    assignee?: (string | null);
    due_date?: (string | null);
    case_id?: (number | null);
    timeline_items?: null;
    tags?: (Array<string> | null);
};

