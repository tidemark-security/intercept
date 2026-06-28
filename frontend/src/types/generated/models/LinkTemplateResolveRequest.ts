/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Request body for resolving enabled link templates for a context item.
 */
export type LinkTemplateResolveRequest = {
    surface?: 'entity' | 'timeline_item';
    entity_type?: ('alert' | 'case' | 'task' | null);
    item?: Record<string, any>;
};

