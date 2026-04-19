/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Admin request to provision the Intercept MCP server in LangFlow.
 */
export type LangFlowSetupRequest = {
    /**
     * Intercept backend API base URL, used to derive the /mcp/streamable/ endpoint
     */
    backend_api_base_url: string;
    /**
     * Username for the dedicated LangFlow automation NHI account
     */
    nhi_username?: string;
    /**
     * Display name for the generated NHI API key
     */
    api_key_name?: string;
    /**
     * Expiration timestamp for the generated NHI API key
     */
    api_key_expires_at?: string;
};

