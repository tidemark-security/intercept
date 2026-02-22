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

/**
 * Base timeline item type union (before recursive replies)
 * Matches the backend CaseTimelineItem Union type
 */
type TimelineItemBase =
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

/**
 * Timeline item with optional recursive replies support
 * Each timeline item can contain an array of nested timeline items as replies
 */
export type TimelineItem = TimelineItemBase & {
  parent_id?: string | null;
  replies?: TimelineItem[] | null;
  /** 
   * For alert/task items on a case timeline, this contains the timeline items
   * from the linked alert or task (populated when include_linked_timelines=true)
   */
  source_timeline_items?: TimelineItem[] | null;
};

/**
 * Type guard to check if an item is a AlertItem
 */
export function isAlertItem(item: TimelineItem): item is AlertItem {
  return item.type === 'alert';
}

/**
 * Type guard to check if an item is a SystemItem
 */
export function isSystemItem(item: TimelineItem): item is SystemItem {
  return item.type === 'system';
}

/**
 * Type guard to check if an item is an InternalActorItem
 */
export function isInternalActorItem(item: TimelineItem): item is InternalActorItem {
  return item.type === 'internal_actor';
}

/**
 * Type guard to check if an item is an ExternalActorItem
 */
export function isExternalActorItem(item: TimelineItem): item is ExternalActorItem {
  return item.type === 'external_actor';
}

/**
 * Type guard to check if an item is a ThreatActorItem
 */
export function isThreatActorItem(item: TimelineItem): item is ThreatActorItem {
  return item.type === 'threat_actor';
}

/**
 * Type guard to check if an item is a NoteItem
 */
export function isNoteItem(item: TimelineItem): item is NoteItem {
  return item.type === 'note';
}

/**
 * Type guard to check if an item is an ObservableItem
 */
export function isObservableItem(item: TimelineItem): item is ObservableItem {
  return item.type === 'observable';
}

/**
 * Type guard to check if an item is a TaskItem
 */
export function isTaskItem(item: TimelineItem): item is TaskItem {
  return item.type === 'task';
}

/**
 * Type guard to check if an item is an EmailItem
 */
export function isEmailItem(item: TimelineItem): item is EmailItem {
  return item.type === 'email';
}

/**
 * Type guard to check if an item is a LinkItem
 */
export function isLinkItem(item: TimelineItem): item is LinkItem {
  return item.type === 'link';
}

/**
 * Type guard to check if an item is an AttachmentItem
 */
export function isAttachmentItem(item: TimelineItem): item is AttachmentItem {
  return item.type === 'attachment';
}

/**
 * Type guard to check if an item is a NetworkTrafficItem
 */
export function isNetworkTrafficItem(item: TimelineItem): item is NetworkTrafficItem {
  return item.type === 'network_traffic';
}

/**
 * Type guard to check if an item is a ProcessItem
 */
export function isProcessItem(item: TimelineItem): item is ProcessItem {
  return item.type === 'process';
}

/**
 * Type guard to check if an item is a RegistryChangeItem
 */
export function isRegistryChangeItem(item: TimelineItem): item is RegistryChangeItem {
  return item.type === 'registry_change';
}

/**
 * Type guard to check if an item is a TTPItem
 */
export function isTTPItem(item: TimelineItem): item is TTPItem {
  return item.type === 'ttp';
}

/**
 * Type guard to check if an item is a ForensicArtifactItem
 */
export function isForensicArtifactItem(item: TimelineItem): item is ForensicArtifactItem {
  return item.type === 'forensic_artifact';
}
