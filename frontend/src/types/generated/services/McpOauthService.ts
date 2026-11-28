/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MCPOAuthClientRead } from '../models/MCPOAuthClientRead';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class McpOauthService {
    /**
     * List Connected Mcp Clients
     * @returns MCPOAuthClientRead Successful Response
     * @throws ApiError
     */
    public static listConnectedMcpClientsApiV1McpOauthClientsGet(): CancelablePromise<Array<MCPOAuthClientRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mcp/oauth/clients',
        });
    }
    /**
     * Revoke Connected Mcp Client
     * @returns void
     * @throws ApiError
     */
    public static revokeConnectedMcpClientApiV1McpOauthClientsConsentIdDelete({
        consentId,
    }: {
        consentId: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/mcp/oauth/clients/{consent_id}',
            path: {
                'consent_id': consentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
