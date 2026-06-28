/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PICERLStage } from './PICERLStage';
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
    picerl_stage?: (PICERLStage | null);
    assignee?: (string | null);
    case_id?: (number | null);
    status?: (TaskStatus | null);
    tags?: (Array<string> | null);
    /**
     * Migration-only override for the task creation timestamp
     */
    created_at?: (string | null);
};

