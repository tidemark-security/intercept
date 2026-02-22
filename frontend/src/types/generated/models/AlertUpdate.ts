/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AlertStatus } from './AlertStatus';
import type { Priority } from './Priority';
/**
 * Schema for updating an alert.
 */
export type AlertUpdate = {
    title?: (string | null);
    description?: (string | null);
    status?: (AlertStatus | null);
    priority?: (Priority | null);
    source?: (string | null);
    assignee?: (string | null);
    timeline_items?: null;
    tags?: (Array<string> | null);
};

