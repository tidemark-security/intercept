/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiKeyRead } from './ApiKeyRead';
import type { LangFlowSetupStep } from './LangFlowSetupStep';
/**
 * Structured result for LangFlow MCP setup orchestration.
 */
export type LangFlowSetupResponse = {
    success: boolean;
    message: string;
    steps?: Array<LangFlowSetupStep>;
    warnings?: Array<string>;
    nhi_user_id?: (string | null);
    nhi_username?: (string | null);
    api_key?: (ApiKeyRead | null);
    mcp_server_name?: (string | null);
    mcp_server_url?: (string | null);
    variable_name?: (string | null);
    flow_assignments?: Record<string, string>;
};

