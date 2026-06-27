/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseTemplateStatus } from './CaseTemplateStatus';
import type { TemplateTaskDefinition } from './TemplateTaskDefinition';
export type CaseTemplateRead = {
    title?: (string | null);
    description?: (string | null);
    status?: CaseTemplateStatus;
    case_tags?: Array<string>;
    template_tasks?: Array<TemplateTaskDefinition>;
    id: number;
    title_normalized?: (string | null);
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string;
    readonly human_id: string;
};

