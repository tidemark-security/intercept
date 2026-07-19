/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ContextCriterion } from './ContextCriterion';
/**
 * Schema for creating shared context.
 */
export type ContextEntryCreate = {
    criteria?: Array<ContextCriterion>;
    body: string;
    expires_at: string;
};

