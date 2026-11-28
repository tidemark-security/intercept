/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SavedFilterQueue } from './SavedFilterQueue';
import type { SavedFilterScope } from './SavedFilterScope';
import type { SavedFilterSnapshot } from './SavedFilterSnapshot';
export type SavedFilterRead = {
    name: string;
    queue: SavedFilterQueue;
    scope: SavedFilterScope;
    filters: SavedFilterSnapshot;
    id: string;
    navigation_icon?: (string | null);
    navigation_position?: (number | null);
};

