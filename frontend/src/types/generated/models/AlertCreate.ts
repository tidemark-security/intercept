/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Priority } from './Priority';
/**
 * Schema for creating an alert.
 */
export type AlertCreate = {
    title: string;
    description?: (string | null);
    priority?: (Priority | null);
    source?: (string | null);
    /**
     * Migration-only override for the alert creation timestamp
     */
    created_at?: (string | null);
};

