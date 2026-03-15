/**
 * Actor Item Handlers
 * 
 * Handlers for actor timeline items:
 * - InternalActorItem
 * - ExternalActorItem
 * - ThreatActorItem
 */

import React from 'react';
import type { TimelineItem } from '@/types/timeline';
import type { InternalActorItem } from '@/types/generated/models/InternalActorItem';
import type { ExternalActorItem } from '@/types/generated/models/ExternalActorItem';
import type { ThreatActorItem } from '@/types/generated/models/ThreatActorItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import { Badge } from '@/components/data-display/Badge';
import type { CardConfig, CardFactoryOptions, CardSystem, ItemCharacteristic } from '../TimelineCardFactory';
import { processCharacteristics } from '../TimelineCardFactory';

import { Biohazard, Briefcase, Building, Cpu, Crown, Key, Mail, MessageSquare, Percent, Phone, Shield, Tag, User, Wrench } from 'lucide-react';
/**
 * Check if item is an InternalActorItem
 */
export function isInternalActorItem(item: TimelineItem): item is TimelineItem & InternalActorItem {
  return item.type === 'internal_actor';
}

/**
 * Check if item is an ExternalActorItem
 */
export function isExternalActorItem(item: TimelineItem): item is TimelineItem & ExternalActorItem {
  return item.type === 'external_actor';
}

/**
 * Check if item is a ThreatActorItem
 */
export function isThreatActorItem(item: TimelineItem): item is TimelineItem & ThreatActorItem {
  return item.type === 'threat_actor';
}

/**
 * Internal actor characteristic priority mapping
 * Higher priority characteristics take precedence for accent display and color
 */
interface ActorCharacteristic {
  priority: number;
  color: CardSystem;
  accentText: string;
  accentIcon: React.ReactNode;
  badgeIcon: React.ReactNode;
  badgeText: string;
}

const INTERNAL_ACTOR_CHARACTERISTICS: Record<string, ActorCharacteristic> = {
  is_high_risk: {
    priority: 1,
    color: 'error',
    accentText: 'High Risk',
    accentIcon: <Biohazard />,
    badgeIcon: <Biohazard />,
    badgeText: 'At Risk',
  },
  is_vip: {
    priority: 2,
    color: 'success',
    accentText: 'VIP',
    accentIcon: <Crown />,
    badgeIcon: <Crown />,
    badgeText: 'VIP',
  },
  is_privileged: {
    priority: 3,
    color: 'warning',
    accentText: 'Privileged',
    accentIcon: <Key />,
    badgeIcon: <Key />,
    badgeText: 'Privileged',
  },
  is_contractor: {
    priority: 4,
    color: 'default',
    accentText: 'Contractor',
    accentIcon: <Wrench />,
    badgeIcon: <Wrench />,
    badgeText: 'Contractor',
  },
  is_service_account: {
    priority: 5,
    color: 'default',
    accentText: 'Service Account',
    accentIcon: <Cpu />,
    badgeIcon: <Cpu />,
    badgeText: 'Service Account',
  },
};

/**
 * Handle InternalActorItem timeline items.
 * 
 * Field mapping:
 * - Line1: User name (most important identifier)
 * - Line2: User ID
 * - Line3: Job title (if present)
 * - Line4: Organization/Department (if present)
 * - characterFlags: User characteristics as chips (VIP, Privileged, etc.)
 * - accentText/accentIcon: Highest priority risk indicator
 * - actionButtons: Automatically generated based on available fields (email, phone, Teams chat, etc.)
 * - Icon: User
 * - Color: Based on highest priority risk indicator
 */
export function handleInternalActorItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isInternalActorItem(item)) {
    throw new Error('Item is not an InternalActorItem');
  }

  const Icon = getTimelineIcon('internal_actor');
  const IconComponent = Icon ? <Icon /> : undefined;

  // Use the generic characteristics processor
  const { color, accentText, accentIcon, characterFlags } = processCharacteristics(item, {
    characteristics: INTERNAL_ACTOR_CHARACTERISTICS,
  });

  return {
    title: item.name ? `${item.name}` : 'Internal Actor',
    line1: item.name || 'Unknown User',
    line1Icon: <User />,
    line2: item.user_id || undefined,
    line2Icon: item.user_id ? <User /> : undefined,
    line3: item.title || undefined,
    line3Icon: item.title ? <Briefcase /> : undefined,
    line4: item.org || undefined,
    line4Icon: item.org ? <Building /> : undefined,
    characterFlags,
    accentText,
    accentIcon,
    baseIcon: IconComponent,
    system: color,
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}

/**
 * Handle ExternalActorItem timeline items.
 * 
 * Field mapping:
 * - Line1: Actor name (most important identifier)
 * - Line2: Organization (if present)
 * - Line3: Contact email (if present)
 * - actionButtons: Automatically generated based on available fields (email, phone, etc.)
 * - Icon: User
 * - Color: default (external actors are neutral unless known malicious)
 */
export function handleExternalActorItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isExternalActorItem(item)) {
    throw new Error('Item is not an ExternalActorItem');
  }

  const Icon = getTimelineIcon('external_actor');
  const IconComponent = Icon ? <Icon /> : undefined;

  return {
    title: item.name ? `${item.name}` : 'External Actor',
    line1: item.name || 'Unknown External Actor',
    line1Icon: <User />,
    line2: item.org || undefined,
    line2Icon: item.org ? <Building /> : undefined,
    line3: item.contact_email || undefined,
    line3Icon: item.contact_email ? <Mail /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}

/**
 * Handle ThreatActorItem timeline items.
 * 
 * Field mapping:
 * - Line1: Threat actor name (most important identifier)
 * - Line2: Tag ID (if present)
 * - Line3: Confidence level (if present)
 * - Icon: User
 * - Color: default (color should only come from characteristics)
 */
export function handleThreatActorItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isThreatActorItem(item)) {
    throw new Error('Item is not a ThreatActorItem');
  }

  const Icon = getTimelineIcon('threat_actor');
  const IconComponent = Icon ? <Icon /> : undefined;

  return {
    title: item.name ? `${item.name}` : 'Threat Actor',
    line1: item.name || 'Unknown Threat Actor',
    line1Icon: <Shield />,
    line2: item.tag_id || undefined,
    line2Icon: item.tag_id ? <Tag /> : undefined,
    line3: item.confidence ? `Confidence: ${item.confidence}%` : undefined,
    line3Icon: item.confidence ? <Percent /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
