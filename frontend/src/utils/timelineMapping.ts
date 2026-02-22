import { Activity, Bell, Blocks, CheckSquare, Code, Cpu, Database, FileText, Fingerprint, Link, Mail, MessageSquare, MessageSquareText, Microscope, Network, Notebook, NotebookPen, Paperclip, Pen, Share2, Target, Terminal, User, UserX } from 'lucide-react';
/**
 * Timeline item type mappings and utilities
 * 
 * This file provides configuration and helper functions for rendering
 * different types of timeline items with appropriate icons and labels.
 */



/**
 * Timeline item type identifiers
 */
export type TimelineItemType =
  | 'observable'
  | 'system'
  | 'internal_actor'
  | 'external_actor'
  | 'threat_actor'
  | 'note'
  | 'email'
  | 'attachment'
  | 'link'
  | 'ttp'
  | 'process'
  | 'network_traffic'
  | 'registry_change'
  | 'forensic_artifact'
  | 'task'
  | 'alert'
  | 'case'
  | 'actor'; // Generic actor type for drafts/forms

/**
 * Centralized mapping of timeline item types to their icon components.
 */
export const TIMELINE_ICONS: Record<TimelineItemType, React.ComponentType<any>> = {
  observable: Fingerprint,
  system: Cpu,
  internal_actor: User,
  external_actor: UserX,
  threat_actor: UserX,
  actor: User, // Generic actor icon
  note: MessageSquareText,
  email: Mail,
  attachment: Paperclip,
  link: Link,
  ttp: Blocks,
  process: Terminal,
  network_traffic: Network,
  registry_change: Database,
  forensic_artifact: Microscope,
  task: CheckSquare,
  alert: Bell,
  case: FileText,
};

/**
 * Configuration for timeline item types
 */
export interface TimelineItemConfig {
  /** Icon component for this timeline item type */
  icon: React.ComponentType<any>;
  /** Human-readable label for this timeline item type */
  label: string;
  /** Action verb for this item (e.g., "added", "flagged", "linked") */
  action: string;
}

/**
 * Complete mapping of timeline item types to their display configuration
 */
export const TIMELINE_ITEM_TYPE_CONFIG: Record<TimelineItemType, TimelineItemConfig> = {
  observable: {
    icon: TIMELINE_ICONS.observable,
    label: 'Observable',
    action: 'flagged',
  },
  system: {
    icon: TIMELINE_ICONS.system,
    label: 'System',
    action: 'linked',
  },
  internal_actor: {
    icon: TIMELINE_ICONS.internal_actor,
    label: 'Internal Actor',
    action: 'identified',
  },
  external_actor: {
    icon: TIMELINE_ICONS.external_actor,
    label: 'External Actor',
    action: 'identified',
  },
  threat_actor: {
    icon: TIMELINE_ICONS.threat_actor,
    label: 'Threat Actor',
    action: 'attributed',
  },
  note: {
    icon: TIMELINE_ICONS.note,
    label: 'Note',
    action: 'added',
  },
  email: {
    icon: TIMELINE_ICONS.email,
    label: 'Email',
    action: 'linked',
  },
  attachment: {
    icon: TIMELINE_ICONS.attachment,
    label: 'Attachment',
    action: 'attached',
  },
  link: {
    icon: TIMELINE_ICONS.link,
    label: 'Link',
    action: 'added',
  },
  ttp: {
    icon: TIMELINE_ICONS.ttp,
    label: 'TTP',
    action: 'mapped',
  },
  process: {
    icon: TIMELINE_ICONS.process,
    label: 'Process',
    action: 'recorded',
  },
  network_traffic: {
    icon: TIMELINE_ICONS.network_traffic,
    label: 'Network Traffic',
    action: 'captured',
  },
  registry_change: {
    icon: TIMELINE_ICONS.registry_change,
    label: 'Registry Change',
    action: 'detected',
  },
  forensic_artifact: {
    icon: TIMELINE_ICONS.forensic_artifact,
    label: 'Forensic Artifact',
    action: 'collected',
  },
  task: {
    icon: TIMELINE_ICONS.task,
    label: 'Task',
    action: 'created',
  },
  alert: {
    icon: TIMELINE_ICONS.alert,
    label: 'Alert',
    action: 'linked',
  },
  case: {
    icon: TIMELINE_ICONS.case,
    label: 'Case',
    action: 'linked',
  },
  actor: {
    icon: TIMELINE_ICONS.actor,
    label: 'Actor',
    action: 'identified',
  },
};

/**
 * Get the icon component for a timeline item type
 * @param type - The timeline item type
 * @returns Icon component or fallback
 */
export function getTimelineItemIcon(type: TimelineItemType | string): React.ComponentType<any> {
  const config = TIMELINE_ITEM_TYPE_CONFIG[type as TimelineItemType];
  return config?.icon || Bell;
}

/**
 * Alias for getTimelineItemIcon for backward compatibility
 */
export const getTimelineIcon = getTimelineItemIcon;

/**
 * Get the human-readable label for a timeline item type
 * @param type - The timeline item type
 * @returns Human-readable label
 */
export function getTimelineItemLabel(type: TimelineItemType | string): string {
  const config = TIMELINE_ITEM_TYPE_CONFIG[type as TimelineItemType];
  return config?.label || 'Event';
}

/**
 * Get the action verb for a timeline item type
 * @param type - The timeline item type
 * @returns Action verb (e.g., "added", "linked", "flagged")
 */
export function getTimelineItemAction(type: TimelineItemType | string): string {
  const config = TIMELINE_ITEM_TYPE_CONFIG[type as TimelineItemType];
  return config?.action || 'added';
}
