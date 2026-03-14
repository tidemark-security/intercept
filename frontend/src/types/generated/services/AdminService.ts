/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccountType } from '../models/AccountType';
import type { AdminCreateNHIRequest } from '../models/AdminCreateNHIRequest';
import type { AdminCreateNHIResponse } from '../models/AdminCreateNHIResponse';
import type { AdminCreateUserRequest } from '../models/AdminCreateUserRequest';
import type { AdminCreateUserResponse } from '../models/AdminCreateUserResponse';
import type { AdminPasskeyRead } from '../models/AdminPasskeyRead';
import type { AdminResetPasswordRequest } from '../models/AdminResetPasswordRequest';
import type { AdminResetPasswordResponse } from '../models/AdminResetPasswordResponse';
import type { AdminUpdateStatusRequest } from '../models/AdminUpdateStatusRequest';
import type { app__api__routes__admin_auth__UserSummary } from '../models/app__api__routes__admin_auth__UserSummary';
import type { AppSettingCreate } from '../models/AppSettingCreate';
import type { AppSettingRead } from '../models/AppSettingRead';
import type { AppSettingUpdate } from '../models/AppSettingUpdate';
import type { EnrichmentAliasCreate } from '../models/EnrichmentAliasCreate';
import type { EnrichmentAliasRead } from '../models/EnrichmentAliasRead';
import type { EnrichmentAliasUpdate } from '../models/EnrichmentAliasUpdate';
import type { EnrichmentProviderStatusRead } from '../models/EnrichmentProviderStatusRead';
import type { UserRole } from '../models/UserRole';
import type { UserStatus } from '../models/UserStatus';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminService {
    /**
     * Get user list for dropdowns
     * Returns lightweight user summaries for assignee dropdowns and filtering. Available to all authenticated users.
     * @returns app__api__routes__admin_auth__UserSummary Successful Response
     * @throws ApiError
     */
    public static getUsersSummaryApiV1AdminAuthUsersSummaryGet({
        userStatus,
        role,
        accountType,
    }: {
        userStatus?: (UserStatus | null),
        role?: (UserRole | null),
        accountType?: (AccountType | null),
    }): CancelablePromise<Array<app__api__routes__admin_auth__UserSummary>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/auth/users/summary',
            query: {
                'user_status': userStatus,
                'role': role,
                'account_type': accountType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List all user accounts
     * Admin endpoint to retrieve all user accounts
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listUsersApiV1AdminAuthUsersGet(): CancelablePromise<Array<Record<string, any>>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/auth/users',
        });
    }
    /**
     * Create a new user account
     * Admin endpoint to provision a new user with temporary credentials
     * @returns AdminCreateUserResponse Successful Response
     * @throws ApiError
     */
    public static createUserApiV1AdminAuthUsersPost({
        requestBody,
    }: {
        requestBody: AdminCreateUserRequest,
    }): CancelablePromise<AdminCreateUserResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/auth/users',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update user account status
     * Admin endpoint to enable or disable a user account
     * @returns void
     * @throws ApiError
     */
    public static updateUserStatusApiV1AdminAuthUsersUserIdStatusPatch({
        userId,
        requestBody,
    }: {
        userId: string,
        requestBody: AdminUpdateStatusRequest,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/admin/auth/users/{user_id}/status',
            path: {
                'user_id': userId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List passkeys for a user
     * @returns AdminPasskeyRead Successful Response
     * @throws ApiError
     */
    public static listUserPasskeysApiV1AdminAuthUsersUserIdPasskeysGet({
        userId,
    }: {
        userId: string,
    }): CancelablePromise<Array<AdminPasskeyRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/auth/users/{user_id}/passkeys',
            path: {
                'user_id': userId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Revoke user passkey
     * @returns void
     * @throws ApiError
     */
    public static revokeUserPasskeyApiV1AdminAuthUsersUserIdPasskeysPasskeyIdDelete({
        userId,
        passkeyId,
    }: {
        userId: string,
        passkeyId: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/admin/auth/users/{user_id}/passkeys/{passkey_id}',
            path: {
                'user_id': userId,
                'passkey_id': passkeyId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Issue an admin-initiated password reset
     * Admin endpoint to force password reset for a user
     * @returns AdminResetPasswordResponse Successful Response
     * @throws ApiError
     */
    public static issuePasswordResetApiV1AdminAuthPasswordResetsPost({
        requestBody,
    }: {
        requestBody: AdminResetPasswordRequest,
    }): CancelablePromise<AdminResetPasswordResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/auth/password-resets',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create a Non-Human Identity (NHI) account
     * Admin endpoint to create an NHI account with an initial API key
     * @returns AdminCreateNHIResponse Successful Response
     * @throws ApiError
     */
    public static createNhiAccountApiV1AdminAuthUsersNhiPost({
        requestBody,
    }: {
        requestBody: AdminCreateNHIRequest,
    }): CancelablePromise<AdminCreateNHIResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/auth/users/nhi',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get All Settings
     * Get all application settings.
     *
     * - **category**: Optional category filter
     *
     * Requires ADMIN role.
     * Returns settings with secret values masked.
     * Environment variables take precedence over database values.
     * @returns AppSettingRead Successful Response
     * @throws ApiError
     */
    public static getAllSettingsApiV1AdminSettingsGet({
        category,
    }: {
        category?: (string | null),
    }): CancelablePromise<Array<AppSettingRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/settings',
            query: {
                'category': category,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Setting
     * Create a new setting.
     *
     * Requires ADMIN role.
     * Secret values will be encrypted automatically.
     * Returns created setting with secret value masked.
     * @returns AppSettingRead Successful Response
     * @throws ApiError
     */
    public static createSettingApiV1AdminSettingsPost({
        requestBody,
    }: {
        requestBody: AppSettingCreate,
    }): CancelablePromise<AppSettingRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/settings',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Setting
     * Get a single setting by key.
     *
     * Requires ADMIN role.
     * Returns setting with secret value masked.
     * Environment variables take precedence over database values.
     * @returns AppSettingRead Successful Response
     * @throws ApiError
     */
    public static getSettingApiV1AdminSettingsKeyGet({
        key,
    }: {
        key: string,
    }): CancelablePromise<AppSettingRead> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/settings/{key}',
            path: {
                'key': key,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Setting
     * Update an existing setting.
     *
     * Requires ADMIN role.
     * Only value and description can be updated.
     * Secret values will be encrypted automatically.
     * Returns updated setting with secret value masked.
     * @returns AppSettingRead Successful Response
     * @throws ApiError
     */
    public static updateSettingApiV1AdminSettingsKeyPut({
        key,
        requestBody,
    }: {
        key: string,
        requestBody: AppSettingUpdate,
    }): CancelablePromise<AppSettingRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/admin/settings/{key}',
            path: {
                'key': key,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Setting
     * Delete a setting.
     *
     * Requires ADMIN role.
     * Returns 204 No Content on success.
     * @returns void
     * @throws ApiError
     */
    public static deleteSettingApiV1AdminSettingsKeyDelete({
        key,
    }: {
        key: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/admin/settings/{key}',
            path: {
                'key': key,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Provider Statuses
     * @returns EnrichmentProviderStatusRead Successful Response
     * @throws ApiError
     */
    public static getProviderStatusesApiV1AdminEnrichmentsProvidersGet(): CancelablePromise<Array<EnrichmentProviderStatusRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/admin/enrichments/providers',
        });
    }
    /**
     * Enqueue Directory Sync
     * @returns any Successful Response
     * @throws ApiError
     */
    public static enqueueDirectorySyncApiV1AdminEnrichmentsProvidersProviderIdDirectorySyncPost({
        providerId,
    }: {
        providerId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/enrichments/providers/{provider_id}/directory-sync',
            path: {
                'provider_id': providerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Alias
     * @returns EnrichmentAliasRead Successful Response
     * @throws ApiError
     */
    public static createAliasApiV1AdminEnrichmentsAliasesPost({
        requestBody,
    }: {
        requestBody: EnrichmentAliasCreate,
    }): CancelablePromise<EnrichmentAliasRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/enrichments/aliases',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Alias
     * @returns EnrichmentAliasRead Successful Response
     * @throws ApiError
     */
    public static updateAliasApiV1AdminEnrichmentsAliasesAliasIdPut({
        aliasId,
        requestBody,
    }: {
        aliasId: number,
        requestBody: EnrichmentAliasUpdate,
    }): CancelablePromise<EnrichmentAliasRead> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/v1/admin/enrichments/aliases/{alias_id}',
            path: {
                'alias_id': aliasId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Alias
     * @returns void
     * @throws ApiError
     */
    public static deleteAliasApiV1AdminEnrichmentsAliasesAliasIdDelete({
        aliasId,
    }: {
        aliasId: number,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/admin/enrichments/aliases/{alias_id}',
            path: {
                'alias_id': aliasId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Clear Cache
     * @returns any Successful Response
     * @throws ApiError
     */
    public static clearCacheApiV1AdminEnrichmentsCacheClearPost({
        providerId,
    }: {
        /**
         * Optional provider identifier to clear
         */
        providerId?: (string | null),
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/admin/enrichments/cache/clear',
            query: {
                'provider_id': providerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
