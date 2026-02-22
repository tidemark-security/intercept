/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for updating a link template.
 */
export type LinkTemplateUpdate = {
    name?: (string | null);
    icon_name?: (string | null);
    tooltip_template?: (string | null);
    url_template?: (string | null);
    field_names?: (Array<string> | null);
    conditions?: (Record<string, any> | null);
    enabled?: (boolean | null);
    display_order?: (number | null);
};

