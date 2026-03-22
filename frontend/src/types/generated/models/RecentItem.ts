/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Priority } from './Priority';
/**
 * A recent item for the dashboard.
 */
export type RecentItem = {
    id: number;
    human_id: string;
    title: string;
    item_type: 'alert' | 'case' | 'task';
    priority?: (Priority | null);
    status: string;
    updated_at: string;
};

