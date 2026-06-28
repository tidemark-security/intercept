/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PICERLStage } from './PICERLStage';
import type { Priority } from './Priority';
/**
 * Task definition stored inside a case runbook JSONB document.
 */
export type RunbookTaskDefinition = {
    title: string;
    description?: (string | null);
    picerl_stage: PICERLStage;
    relative_due_seconds?: (number | null);
    priority?: (Priority | null);
    tags?: Array<string>;
};

