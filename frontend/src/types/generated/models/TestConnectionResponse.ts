/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LangFlowConnectionCheck } from './LangFlowConnectionCheck';
/**
 * Response from connection test.
 */
export type TestConnectionResponse = {
    checks?: Array<LangFlowConnectionCheck>;
    success: boolean;
    message: string;
};

