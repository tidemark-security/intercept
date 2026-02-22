/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Priority } from './Priority';
import type { TaskStatus } from './TaskStatus';
/**
 * Schema for creating a task.
 */
export type TaskCreate = {
    title: string;
    description?: (string | null);
    priority?: Priority;
    due_date?: (string | null);
    assignee?: (string | null);
    case_id?: (number | null);
    status?: (TaskStatus | null);
};

