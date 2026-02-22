/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MitreService {
    /**
     * Search Attack Objects
     * Search MITRE ATT&CK objects by ID, name, or description.
     *
     * Returns matching techniques, tactics, groups, and software sorted by relevance:
     * - Exact ID matches rank highest
     * - Name matches rank higher than description matches
     *
     * Example queries:
     * - "T1059" - find technique by ID
     * - "PowerShell" - find techniques related to PowerShell
     * - "credential" - find techniques involving credentials
     * @returns any Successful Response
     * @throws ApiError
     */
    public static searchAttackObjectsApiV1MitreSearchGet({
        q,
        types,
        limit = 20,
    }: {
        /**
         * Search query (ID, name, or keyword)
         */
        q: string,
        /**
         * Object types to search: technique, tactic, group, software, mitigation, campaign
         */
        types?: (Array<string> | null),
        /**
         * Maximum results to return
         */
        limit?: number,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/search',
            query: {
                'q': q,
                'types': types,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Techniques
     * List all MITRE ATT&CK techniques.
     *
     * Returns techniques sorted alphabetically by name.
     * Each technique includes:
     * - attack_id: The technique ID (e.g., T1059)
     * - name: Human-readable name
     * - tactics: Associated tactics
     * - url: Link to MITRE ATT&CK page
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listTechniquesApiV1MitreTechniquesGet({
        limit = 100,
        includeSubtechniques = true,
    }: {
        /**
         * Maximum techniques to return
         */
        limit?: number,
        /**
         * Include sub-techniques (e.g., T1059.001)
         */
        includeSubtechniques?: boolean,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/techniques',
            query: {
                'limit': limit,
                'include_subtechniques': includeSubtechniques,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Technique
     * Get a specific MITRE ATT&CK technique by ID.
     *
     * Supports both techniques (T1059) and sub-techniques (T1059.001).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getTechniqueApiV1MitreTechniquesAttackIdGet({
        attackId,
    }: {
        attackId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/techniques/{attack_id}',
            path: {
                'attack_id': attackId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Tactics
     * List all MITRE ATT&CK tactics.
     *
     * Returns all 14 tactics in the Enterprise ATT&CK matrix:
     * - Reconnaissance (TA0043)
     * - Resource Development (TA0042)
     * - Initial Access (TA0001)
     * - Execution (TA0002)
     * - Persistence (TA0003)
     * - Privilege Escalation (TA0004)
     * - Defense Evasion (TA0005)
     * - Credential Access (TA0006)
     * - Discovery (TA0007)
     * - Lateral Movement (TA0008)
     * - Collection (TA0009)
     * - Command and Control (TA0011)
     * - Exfiltration (TA0010)
     * - Impact (TA0040)
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listTacticsApiV1MitreTacticsGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/tactics',
        });
    }
    /**
     * Get Tactic
     * Get a specific MITRE ATT&CK tactic by ID.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getTacticApiV1MitreTacticsAttackIdGet({
        attackId,
    }: {
        attackId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/tactics/{attack_id}',
            path: {
                'attack_id': attackId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Group
     * Get a specific MITRE ATT&CK threat group by ID.
     *
     * Group IDs start with 'G' (e.g., G0001 for Axiom).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getGroupApiV1MitreGroupsAttackIdGet({
        attackId,
    }: {
        attackId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/groups/{attack_id}',
            path: {
                'attack_id': attackId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Software
     * Get a specific MITRE ATT&CK software/tool by ID.
     *
     * Software IDs start with 'S' (e.g., S0002 for Mimikatz).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getSoftwareApiV1MitreSoftwareAttackIdGet({
        attackId,
    }: {
        attackId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/software/{attack_id}',
            path: {
                'attack_id': attackId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Lookup Attack Object
     * Look up any MITRE ATT&CK object by ID.
     *
     * Automatically detects the object type from the ID prefix:
     * - T: Technique (e.g., T1059, T1059.001)
     * - TA: Tactic (e.g., TA0001)
     * - G: Group (e.g., G0001)
     * - S: Software (e.g., S0002)
     * - M: Mitigation (e.g., M1036)
     * - C: Campaign (e.g., C0001)
     * - DS: Data Source (e.g., DS0001)
     * @returns any Successful Response
     * @throws ApiError
     */
    public static lookupAttackObjectApiV1MitreLookupAttackIdGet({
        attackId,
    }: {
        attackId: string,
    }): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/mitre/lookup/{attack_id}',
            path: {
                'attack_id': attackId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
