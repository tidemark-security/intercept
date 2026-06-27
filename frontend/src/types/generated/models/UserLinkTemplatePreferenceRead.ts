/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for reading per-user link template preferences.
 */
export type UserLinkTemplatePreferenceRead = {
    /**
     * Global link template this preference applies to
     */
    template_id: number;
    /**
     * Whether this user wants the template shown
     */
    enabled?: boolean;
    /**
     * User-scoped interpolation values referenced as {{user.key}}
     */
    values?: Record<string, string>;
    id: number;
    user_id: string;
    created_at: string;
    updated_at: string;
};

