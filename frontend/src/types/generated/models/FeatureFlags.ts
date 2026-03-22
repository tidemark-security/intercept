/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Public feature flags for frontend.
 */
export type FeatureFlags = {
    /**
     * Whether AI triage is available (LangFlow alert triage flow is configured)
     */
    ai_triage_enabled?: boolean;
    /**
     * Whether to automatically enqueue triage when alerts are created
     */
    ai_triage_auto_enqueue?: boolean;
    /**
     * Recommended case closure tags for the close case modal
     */
    case_closure_recommended_tags?: Array<string>;
};

