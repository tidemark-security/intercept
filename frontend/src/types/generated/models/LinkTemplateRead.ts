/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for reading a link template.
 */
export type LinkTemplateRead = {
    /**
     * Unique identifier for this template type (e.g., 'virustotal-domain')
     */
    template_id: string;
    /**
     * Human-readable name of the link template
     */
    name: string;
    /**
     * Icon identifier (e.g., 'FeatherMail', 'VirusTotalIcon')
     */
    icon_name: string;
    /**
     * Tooltip text with {{variable}} placeholders for interpolation
     */
    tooltip_template: string;
    /**
     * URL template with {{variable}} placeholders for interpolation
     */
    url_template: string;
    /**
     * Array of field names this template applies to
     */
    field_names?: (Array<string> | null);
    /**
     * Object of field/value pairs that must match
     */
    conditions?: (Record<string, any> | null);
    /**
     * Whether this template is currently active
     */
    enabled?: boolean;
    /**
     * Sort order for display (lower numbers first)
     */
    display_order?: number;
    id: number;
    created_at: string;
    updated_at: string;
};

