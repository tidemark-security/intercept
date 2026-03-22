/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SettingType } from './SettingType';
/**
 * Schema for creating a setting.
 */
export type AppSettingCreate = {
    /**
     * Setting key (lowercase, alphanumeric, dots, underscores, hyphens)
     */
    key: string;
    /**
     * Setting value (encrypted if is_secret=true)
     */
    value?: (string | null);
    /**
     * Type hint for value
     */
    value_type?: SettingType;
    /**
     * Whether value should be encrypted
     */
    is_secret?: boolean;
    /**
     * Human-readable description
     */
    description?: (string | null);
    /**
     * Grouping category
     */
    category: string;
};

