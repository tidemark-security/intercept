/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for updating a personal link template.
 */
export type PersonalLinkTemplateUpdate = {
    name?: (string | null);
    icon_name?: (string | null);
    tooltip_template?: (string | null);
    url_template?: (string | null);
    field_names?: (Array<string> | null);
    conditions?: (Record<string, any> | null);
    surface_scopes?: (Array<'entity' | 'timeline_item'> | null);
    entity_types?: (Array<'alert' | 'case' | 'task'> | null);
    enabled?: (boolean | null);
    display_order?: (number | null);
};

