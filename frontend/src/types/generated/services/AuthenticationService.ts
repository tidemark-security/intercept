/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LoginRequest } from '../models/LoginRequest';
import type { LoginResponse } from '../models/LoginResponse';
import type { OIDCConfigResponse } from '../models/OIDCConfigResponse';
import type { OIDCTestResponse } from '../models/OIDCTestResponse';
import type { PasskeyBeginAuthenticationRequest } from '../models/PasskeyBeginAuthenticationRequest';
import type { PasskeyBeginRegistrationRequest } from '../models/PasskeyBeginRegistrationRequest';
import type { PasskeyBeginResponse } from '../models/PasskeyBeginResponse';
import type { PasskeyFinishAuthenticationRequest } from '../models/PasskeyFinishAuthenticationRequest';
import type { PasskeyFinishRegistrationRequest } from '../models/PasskeyFinishRegistrationRequest';
import type { PasskeyRead } from '../models/PasskeyRead';
import type { PasskeyRenameRequest } from '../models/PasskeyRenameRequest';
import type { PasswordChangeRequest } from '../models/PasswordChangeRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AuthenticationService {
    /**
     * Login
     * Authenticate with username and password.
     *
     * Returns a secure HTTP-only session cookie on success.
     *
     * **Error Responses:**
     * - **401 Unauthorized**: Invalid credentials
     * - **403 Forbidden**: Account is disabled
     * - **423 Locked**: Account locked due to repeated failures (includes retry information)
     * - **429 Too Many Requests**: Rate limit exceeded
     *
     * **Security:**
     * - Passwords are verified using Argon2id hashing
     * - Failed attempts are counted and trigger lockout after threshold
     * - Rate limiting prevents brute-force attacks
     * - All attempts are logged for audit
     * @returns LoginResponse Successful Response
     * @throws ApiError
     */
    public static loginApiV1AuthLoginPost({
        requestBody,
    }: {
        requestBody: LoginRequest,
    }): CancelablePromise<LoginResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/login',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Logout
     * Terminate the active session.
     *
     * Revokes the session and clears the session cookie.
     *
     * **Authentication Required**: Must have active session cookie.
     *
     * **Error Responses:**
     * - **401 Unauthorized**: No active session or session invalid
     * @returns void
     * @throws ApiError
     */
    public static logoutApiV1AuthLogoutPost(): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/logout',
        });
    }
    /**
     * Begin Passkey Registration
     * Begin WebAuthn registration for the authenticated human user.
     * @returns PasskeyBeginResponse Successful Response
     * @throws ApiError
     */
    public static beginPasskeyRegistrationApiV1AuthPasskeysRegisterOptionsPost({
        requestBody,
    }: {
        requestBody: PasskeyBeginRegistrationRequest,
    }): CancelablePromise<PasskeyBeginResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/passkeys/register/options',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Finish Passkey Registration
     * Verify WebAuthn registration ceremony and persist passkey.
     * @returns PasskeyRead Successful Response
     * @throws ApiError
     */
    public static finishPasskeyRegistrationApiV1AuthPasskeysRegisterVerifyPost({
        requestBody,
    }: {
        requestBody: PasskeyFinishRegistrationRequest,
    }): CancelablePromise<PasskeyRead> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/passkeys/register/verify',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Begin Passkey Authentication
     * Begin username-first WebAuthn authentication.
     * @returns PasskeyBeginResponse Successful Response
     * @throws ApiError
     */
    public static beginPasskeyAuthenticationApiV1AuthPasskeysAuthenticateOptionsPost({
        requestBody,
    }: {
        requestBody: PasskeyBeginAuthenticationRequest,
    }): CancelablePromise<PasskeyBeginResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/passkeys/authenticate/options',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Finish Passkey Authentication
     * Complete WebAuthn authentication and issue a normal application session.
     * @returns LoginResponse Successful Response
     * @throws ApiError
     */
    public static finishPasskeyAuthenticationApiV1AuthPasskeysAuthenticateVerifyPost({
        requestBody,
    }: {
        requestBody: PasskeyFinishAuthenticationRequest,
    }): CancelablePromise<LoginResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/passkeys/authenticate/verify',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Own Passkeys
     * @returns PasskeyRead Successful Response
     * @throws ApiError
     */
    public static listOwnPasskeysApiV1AuthPasskeysGet(): CancelablePromise<Array<PasskeyRead>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/passkeys',
        });
    }
    /**
     * Rename Own Passkey
     * @returns PasskeyRead Successful Response
     * @throws ApiError
     */
    public static renameOwnPasskeyApiV1AuthPasskeysPasskeyIdPatch({
        passkeyId,
        requestBody,
    }: {
        passkeyId: string,
        requestBody: PasskeyRenameRequest,
    }): CancelablePromise<PasskeyRead> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/v1/auth/passkeys/{passkey_id}',
            path: {
                'passkey_id': passkeyId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Revoke Own Passkey
     * @returns void
     * @throws ApiError
     */
    public static revokeOwnPasskeyApiV1AuthPasskeysPasskeyIdDelete({
        passkeyId,
    }: {
        passkeyId: string,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/v1/auth/passkeys/{passkey_id}',
            path: {
                'passkey_id': passkeyId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Session
     * Get the current session information.
     *
     * Returns user and session details if there's an active session cookie.
     * This endpoint is used to validate and refresh sessions on app load.
     *
     * **Authentication Required**: Must have active session cookie.
     *
     * **Error Responses:**
     * - **401 Unauthorized**: No active session or session invalid/expired
     * @returns LoginResponse Successful Response
     * @throws ApiError
     */
    public static getSessionApiV1AuthSessionGet(): CancelablePromise<LoginResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/session',
        });
    }
    /**
     * Change Password
     * Change password for the authenticated user.
     *
     * Validates the current password and updates to new password if policy is met.
     * All other active sessions for this user are revoked upon successful change.
     *
     * **Authentication Required**: Must have active session cookie.
     *
     * **Password Policy:**
     * - Minimum 12 characters
     * - Must include uppercase, lowercase, number, and special character
     *
     * **Error Responses:**
     * - **400 Bad Request**: New password doesn't meet policy requirements
     * - **401 Unauthorized**: Current password is incorrect or no active session
     * @returns void
     * @throws ApiError
     */
    public static changePasswordApiV1AuthPasswordChangePost({
        requestBody,
    }: {
        requestBody: PasswordChangeRequest,
    }): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/auth/password/change',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Oidc Config
     * @returns OIDCConfigResponse Successful Response
     * @throws ApiError
     */
    public static getOidcConfigApiV1AuthOidcConfigGet(): CancelablePromise<OIDCConfigResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/oidc/config',
        });
    }
    /**
     * Begin Oidc Login
     * @returns any Successful Response
     * @throws ApiError
     */
    public static beginOidcLoginApiV1AuthOidcLoginGet({
        next,
    }: {
        /**
         * Absolute frontend URL to return to after authentication
         */
        next: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/oidc/login',
            query: {
                'next': next,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Finish Oidc Login
     * @returns any Successful Response
     * @throws ApiError
     */
    public static finishOidcLoginApiV1AuthOidcCallbackGet({
        code,
        state,
    }: {
        code: string,
        state: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/oidc/callback',
            query: {
                'code': code,
                'state': state,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Test Oidc Discovery
     * @returns OIDCTestResponse Successful Response
     * @throws ApiError
     */
    public static testOidcDiscoveryApiV1AuthOidcTestDiscoveryGet(): CancelablePromise<OIDCTestResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/auth/oidc/test-discovery',
        });
    }
}
