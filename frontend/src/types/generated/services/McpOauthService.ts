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
     * Protected Resource Metadata
     * @returns any Successful Response
     * @throws ApiError
     */
    public static protectedResourceMetadataWellKnownOauthProtectedResourceResourcePathGet({
        resourcePath,
    }: {
        resourcePath: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/.well-known/oauth-protected-resource{resource_path}',
            path: {
                'resource_path': resourcePath,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Authorization Server Metadata
     * @returns any Successful Response
     * @throws ApiError
     */
    public static authorizationServerMetadataWellKnownOauthAuthorizationServerGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/.well-known/oauth-authorization-server',
        });
    }
    /**
     * Register Client
     * @returns any Successful Response
     * @throws ApiError
     */
    public static registerClientOauthRegisterPost(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/oauth/register',
        });
    }
    /**
     * Token
     * @returns any Successful Response
     * @throws ApiError
     */
    public static tokenOauthTokenPost(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/oauth/token',
        });
    }
    /**
     * Revoke Token
     * @returns any Successful Response
     * @throws ApiError
     */
    public static revokeTokenOauthRevokePost(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/oauth/revoke',
        });
    }
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
