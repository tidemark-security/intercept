/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiKeyCreateResponse } from '../models/ApiKeyCreateResponse';
import type { ApiKeyRead } from '../models/ApiKeyRead';
import type { CreateApiKeyRequest } from '../models/CreateApiKeyRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ApiKeysService {
    /**
     * Create Api Key
     * Create a new API key.
     *
     * **IMPORTANT**: The full API key is only returned in this response.
     * Store it securely - it cannot be retrieved again.
     *
     * Regular users can only create keys for themselves.
     * Admins can create keys for other users only when the target account is NHI.
     *
     * **Authentication**: Session cookie or API key
     *
     * **Returns**: The created API key with the full key value (one-time only)
     * @returns ApiKeyCreateResponse Successful Response
     * @throws ApiError
     */
    public static createApiKeyApiV1ApiKeysPost({
        requestBody,
    }: {
        requestBody: CreateApiKeyRequest,
    }): CancelablePromise<ApiKeyCreateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/api-keys',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Api Keys
     * List API keys.
     *
     * Regular users can only list their own keys.
     * Admins can list any user's keys by specifying `user_id`.
     *
     * **Authentication**: Session cookie or API key
     *
     * **Query Parameters**:
     * - `include_revoked`: Include revoked keys (default: false)
     * - `user_id`: Target user ID (admin-only, defaults to current user)
     *
     * **Returns**: List of API key metadata (never includes the actual key value)
     * @returns ApiKeyRead Successful Response
     * @throws ApiError
     */
    public static listApiKeysApiV1ApiKeysGet({
        includeRevoked = false,
        userId,
    }: {
        includeRevoked?: boolean,
        userId?: (string | null),
    }): CancelablePromise<Array<ApiKeyRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/api-keys',
            query: {
                'include_revoked': includeRevoked,
                'user_id': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Api Key
     * Get details of a specific API key.
     *
     * Regular users can only view their own keys.
     * Admins can view any key.
     *
     * **Authentication**: Session cookie or API key
     *
     * **Returns**: API key metadata (never includes the actual key value)
     * @returns ApiKeyRead Successful Response
     * @throws ApiError
     */
    public static getApiKeyApiV1ApiKeysApiKeyIdGet({
        apiKeyId,
    }: {
        apiKeyId: string,
    }): CancelablePromise<ApiKeyRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/api-keys/{api_key_id}',
            path: {
                'api_key_id': apiKeyId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Revoke Api Key
     * Revoke an API key.
     *
     * Once revoked, an API key cannot be used for authentication.
     * This action cannot be undone.
     *
     * Regular users can only revoke their own keys.
     * Admins can revoke any key.
     *
     * **Authentication**: Session cookie or API key
     * @returns void
     * @throws ApiError
     */
    public static revokeApiKeyApiV1ApiKeysApiKeyIdDelete({
        apiKeyId,
    }: {
        apiKeyId: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/api-keys/{api_key_id}',
            path: {
                'api_key_id': apiKeyId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
