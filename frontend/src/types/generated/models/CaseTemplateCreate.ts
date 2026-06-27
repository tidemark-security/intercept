/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CaseTemplateStatus } from './CaseTemplateStatus';
import type { TemplateTaskDefinition } from './TemplateTaskDefinition';
export type CaseTemplateCreate = {
    title?: (string | null);
    description?: (string | null);
    status?: (CaseTemplateStatus | null);
    case_tags?: Array<string>;
    template_tasks?: Array<TemplateTaskDefinition>;
};

