/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Portable JSON representation shared by public and personal templates.
 */
export type PortableLinkTemplate = {
    template_id: string;
    name: string;
    icon_name: string;
    tooltip_template: string;
    url_template: string;
    field_names?: (Array<string> | null);
    conditions?: (Record<string, any> | null);
    surface_scopes?: Array<'entity' | 'timeline_item'>;
    entity_types?: (Array<'alert' | 'case' | 'task'> | null);
    enabled?: boolean;
    display_order?: number;
};

