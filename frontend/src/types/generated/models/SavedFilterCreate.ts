/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SavedFilterQueue } from './SavedFilterQueue';
import type { SavedFilterScope } from './SavedFilterScope';
import type { SavedFilterSnapshot } from './SavedFilterSnapshot';
export type SavedFilterCreate = {
    name: string;
    queue: SavedFilterQueue;
    scope: SavedFilterScope;
    filters: SavedFilterSnapshot;
};

