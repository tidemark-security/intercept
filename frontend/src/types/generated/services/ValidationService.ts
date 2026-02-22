/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ValidationService {
    /**
     * Get Validation Rules
     * Get all validation rules.
     *
     * Returns a flat dictionary of validation rules keyed by rule identifier
     * (e.g., "observable.IP", "network.src_port"). Each rule includes:
     * - key: Rule identifier
     * - label: Human-readable label
     * - pattern: Regex pattern (if applicable)
     * - allowed_values: List of valid values (if applicable, e.g., for enums)
     * - examples: Example valid values
     * - error_message: Error message to display on validation failure
     *
     * Clients should cache this response (recommended TTL: 1 hour).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getValidationRulesApiV1ValidationRulesGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/validation/rules',
        });
    }
}
