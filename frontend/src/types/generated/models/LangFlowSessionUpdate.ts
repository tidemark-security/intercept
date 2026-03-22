/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SessionStatus } from './SessionStatus';
/**
 * Schema for updating a session.
 */
export type LangFlowSessionUpdate = {
    /**
     * Session title
     */
    title?: (string | null);
    context?: (Record<string, any> | null);
    status?: (SessionStatus | null);
};

