/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ContextCriterion } from './ContextCriterion';
/**
 * Schema for reading shared context.
 */
export type ContextEntryRead = {
    id: number;
    criteria?: Array<ContextCriterion>;
    body: string;
    author: string;
    created_at: string;
    updated_at: string;
    expires_at: string;
    expired_at?: (string | null);
};

