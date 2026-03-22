/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Priority } from './Priority';
/**
 * Schema for creating a case.
 */
export type CaseCreate = {
    title: string;
    description?: (string | null);
    priority?: Priority;
    tags?: (Array<string> | null);
    assignee?: (string | null);
};

