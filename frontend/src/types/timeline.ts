/**
 * Timeline item type unions and type guards
 * 
 * This file provides TypeScript unions and type guards for working with
 * the various timeline item types from the backend.
 */

import type { SystemItem } from '@/types/generated/models/SystemItem';
import type { InternalActorItem } from '@/types/generated/models/InternalActorItem';
import type { ExternalActorItem } from '@/types/generated/models/ExternalActorItem';
import type { ThreatActorItem } from '@/types/generated/models/ThreatActorItem';
import type { AlertItem } from '@/types/generated/models/AlertItem';
import type { AttachmentItem } from '@/types/generated/models/AttachmentItem';
import type { CaseItem } from '@/types/generated/models/CaseItem';
import type { EmailItem } from '@/types/generated/models/EmailItem';
import type { ForensicArtifactItem } from '@/types/generated/models/ForensicArtifactItem';
import type { LinkItem } from '@/types/generated/models/LinkItem';
import type { NetworkTrafficItem } from '@/types/generated/models/NetworkTrafficItem';
import type { NoteItem } from '@/types/generated/models/NoteItem';
import type { ObservableItem } from '@/types/generated/models/ObservableItem';
import type { ProcessItem } from '@/types/generated/models/ProcessItem';
import type { RegistryChangeItem } from '@/types/generated/models/RegistryChangeItem';
import type { TaskItem } from '@/types/generated/models/TaskItem';
import type { TTPItem } from '@/types/generated/models/TTPItem';
import type { TimelineItemAudit } from '@/types/generated/models/TimelineItemAudit';

export interface DeletedItem {
  id: string;
  type: '_deleted';
  created_by?: string | null;
  created_at?: string | null;
  timestamp?: string | null;
  description?: string | null;
  enrichment_status?: string | null;
  flagged?: boolean;
  highlighted?: boolean;
  deleted_at: string;
  deleted_by: string;
  original_type: string;
  original_created_at?: string | null;
  original_created_by?: string | null;
  parent_id?: string | null;
  replies?: Record<string, TimelineItem> | null;
}

interface RecursiveTimelineFields {
  parent_id?: string | null;
  replies?: Record<string, TimelineItem> | null;
  audit?: TimelineItemAudit | null;
  source_timeline_items?: Record<string, TimelineItem> | null;
}

type WithRecursiveTimelineFields<T> = T extends unknown
  ? Omit<T, keyof RecursiveTimelineFields> & RecursiveTimelineFields
  : never;

/**
 * Base timeline item type union (before recursive replies)
 * Matches the backend CaseTimelineItem Union type
 */
type TimelineItemBase =
  | DeletedItem
  | InternalActorItem
  | ExternalActorItem
  | ThreatActorItem
  | AlertItem
  | AttachmentItem
  | CaseItem
  | EmailItem
  | ForensicArtifactItem
  | LinkItem
  | NetworkTrafficItem
  | NoteItem
  | ObservableItem
  | ProcessItem
  | RegistryChangeItem
  | SystemItem
  | TaskItem
  | TTPItem;

export type RecursiveTimelineItem<T extends TimelineItemBase = TimelineItemBase> = WithRecursiveTimelineFields<T>;

/**
 * Timeline item with optional recursive replies support
 * Each timeline item can contain nested timeline items keyed by reply ID
 */
export type TimelineItem = WithRecursiveTimelineFields<TimelineItemBase>;

/**
 * Type guard to check if an item is a AlertItem
 */
export function isAlertItem(item: TimelineItem): item is RecursiveTimelineItem<AlertItem> {
  return item.type === 'alert';
}

export function isDeletedItem(item: TimelineItem): item is RecursiveTimelineItem<DeletedItem> {
  return item.type === '_deleted';
}

/**
 * Type guard to check if an item is a SystemItem
 */
export function isSystemItem(item: TimelineItem): item is RecursiveTimelineItem<SystemItem> {
  return item.type === 'system';
}

/**
 * Type guard to check if an item is an InternalActorItem
 */
export function isInternalActorItem(item: TimelineItem): item is RecursiveTimelineItem<InternalActorItem> {
  return item.type === 'internal_actor';
}

/**
 * Type guard to check if an item is an ExternalActorItem
 */
export function isExternalActorItem(item: TimelineItem): item is RecursiveTimelineItem<ExternalActorItem> {
  return item.type === 'external_actor';
}

/**
 * Type guard to check if an item is a ThreatActorItem
 */
export function isThreatActorItem(item: TimelineItem): item is RecursiveTimelineItem<ThreatActorItem> {
  return item.type === 'threat_actor';
}

/**
 * Type guard to check if an item is a NoteItem
 */
export function isNoteItem(item: TimelineItem): item is RecursiveTimelineItem<NoteItem> {
  return item.type === 'note';
}

/**
 * Type guard to check if an item is an ObservableItem
 */
export function isObservableItem(item: TimelineItem): item is RecursiveTimelineItem<ObservableItem> {
  return item.type === 'observable';
}

/**
 * Type guard to check if an item is a TaskItem
 */
export function isTaskItem(item: TimelineItem): item is RecursiveTimelineItem<TaskItem> {
  return item.type === 'task';
}

/**
 * Type guard to check if an item is an EmailItem
 */
export function isEmailItem(item: TimelineItem): item is RecursiveTimelineItem<EmailItem> {
  return item.type === 'email';
}

/**
 * Type guard to check if an item is a LinkItem
 */
export function isLinkItem(item: TimelineItem): item is RecursiveTimelineItem<LinkItem> {
  return item.type === 'link';
}

/**
 * Type guard to check if an item is an AttachmentItem
 */
export function isAttachmentItem(item: TimelineItem): item is RecursiveTimelineItem<AttachmentItem> {
  return item.type === 'attachment';
}

/**
 * Type guard to check if an item is a NetworkTrafficItem
 */
export function isNetworkTrafficItem(item: TimelineItem): item is RecursiveTimelineItem<NetworkTrafficItem> {
  return item.type === 'network_traffic';
}

/**
 * Type guard to check if an item is a ProcessItem
 */
export function isProcessItem(item: TimelineItem): item is RecursiveTimelineItem<ProcessItem> {
  return item.type === 'process';
}

/**
 * Type guard to check if an item is a RegistryChangeItem
 */
export function isRegistryChangeItem(item: TimelineItem): item is RecursiveTimelineItem<RegistryChangeItem> {
  return item.type === 'registry_change';
}

/**
 * Type guard to check if an item is a TTPItem
 */
export function isTTPItem(item: TimelineItem): item is RecursiveTimelineItem<TTPItem> {
  return item.type === 'ttp';
}

/**
 * Type guard to check if an item is a ForensicArtifactItem
 */
export function isForensicArtifactItem(item: TimelineItem): item is RecursiveTimelineItem<ForensicArtifactItem> {
  return item.type === 'forensic_artifact';
}
