/**
 * Draft data types for localStorage persistence of timeline item forms
 */

export type TimelineItemType =
  | "note"
  | "observable"
  | "system"
  | "actor"
  | "email"
  | "link"
  | "task"
  | "attachment"
  | "network_traffic"
  | "process"
  | "registry_change"
  | "ttp"
  | "forensic_artifact"
  | "case_edit"
  | "task_edit";

/**
 * Base form data structure shared across all timeline item types
 */
export interface BaseFormData {
  description?: string;
  tags?: string[];
  timestamp?: string;
}

/**
 * Note-specific form data
 */
export interface NoteFormData extends BaseFormData {
  // Notes only have base fields
}

/**
 * Observable (IOC) form data
 */
export interface ObservableFormData extends BaseFormData {
  indicator_type?: string;
  indicator_value?: string;
  confidence_level?: string;
}

/**
 * System form data
 */
export interface SystemFormData extends BaseFormData {
  hostname?: string;
  ip_address?: string;
  system_type?: string;
  is_critical?: boolean;
  is_internet_facing?: boolean;
  cmdb_id?: string;
}

/**
 * Actor form data
 */
export interface ActorFormData extends BaseFormData {
  name?: string;
  actor_type?: string;
  title?: string;
  org?: string;
  is_vip?: boolean;
  is_privileged?: boolean;
  is_high_risk?: boolean;
}

/**
 * Union type for all timeline item form data
 */
export type TimelineItemFormData =
  | NoteFormData
  | ObservableFormData
  | SystemFormData
  | ActorFormData
  | BaseFormData; // Generic fallback for other types

/**
 * Draft data structure stored in localStorage
 */
export interface DraftData {
  /** Schema version for future migrations */
  version: number;
  /** Alert ID this draft belongs to (deprecated, use entityId) */
  alertId?: number;
  /** Entity ID (alert, case, or task) this draft belongs to */
  entityId: number;
  /** Entity type ('alert', 'case', or 'task') */
  entityType: 'alert' | 'case' | 'task';
  /** Type of timeline item being created */
  itemType: TimelineItemType;
  /** ISO 8601 timestamp when draft was created */
  createdAt: string;
  /** ISO 8601 timestamp when draft expires (createdAt + 24 hours) */
  expiresAt: string;
  /** Form field values */
  formData: TimelineItemFormData;
}

/**
 * Right Dock UI state stored per alert
 */
export interface RightDockState {
  /** Whether the right dock is open */
  isOpen: boolean;
  /** Type of timeline item form currently displayed */
  itemType: TimelineItemType;
  /** ISO 8601 timestamp when state was last updated */
  lastUpdated: string;
}
