/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TimelineGraphDocument } from './TimelineGraphDocument';
export type TimelineGraphRead = {
    entity_type: 'case' | 'task';
    entity_id: number;
    graph?: TimelineGraphDocument;
    revision: number;
    created_at?: (string | null);
    updated_at?: (string | null);
    created_by?: (string | null);
    updated_by?: (string | null);
};

