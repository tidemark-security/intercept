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

import type { CardConfig, CardFactoryOptions, CardMetadataItem, CardSystem, ItemCharacteristic } from '../TimelineCardFactory';
import { processCharacteristics } from '../TimelineCardFactory';

import { Biohazard, Briefcase, Building, Cpu, Crown, IdCard, Key, Mail, MapPin, Percent, Phone, ShieldOff, Tag, Users, Wrench } from 'lucide-react';
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
  is_disabled: {
    priority: 6,
    color: 'warning',
    accentText: 'Disabled',
    accentIcon: <ShieldOff />,
    badgeIcon: <ShieldOff />,
    badgeText: 'Disabled',
  },
};

type EnrichmentRecord = Record<string, unknown>;

function asRecord(value: unknown): EnrichmentRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as EnrichmentRecord
    : null;
}

function getString(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }

  if (typeof value === 'number') {
    return String(value);
  }

  if (Array.isArray(value)) {
    return value.map(getString).find(Boolean);
  }

  return undefined;
}

function firstString(...values: unknown[]): string | undefined {
  return values.map(getString).find(Boolean);
}

function getBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function getInternalActorEnrichments(item: InternalActorItem): {
  googleWorkspace: EnrichmentRecord | null;
  entraId: EnrichmentRecord | null;
  ldap: EnrichmentRecord | null;
} {
  const enrichments = asRecord((item as InternalActorItem & { enrichments?: unknown }).enrichments);

  return {
    googleWorkspace: asRecord(enrichments?.google_workspace),
    entraId: asRecord(enrichments?.entra_id),
    ldap: asRecord(enrichments?.ldap),
  };
}

function getManagerDisplay(item: InternalActorItem, entraId: EnrichmentRecord | null, ldap: EnrichmentRecord | null): string | undefined {
  return firstString(
    entraId?.manager_name,
    entraId?.manager_email,
    entraId?.manager_upn,
    ldap?.manager_cn,
    item.manager_id ? `Manager ID ${item.manager_id}` : undefined
  );
}

function isInternalActorExplicitlyDisabled(
  googleWorkspace: EnrichmentRecord | null,
  entraId: EnrichmentRecord | null
): boolean {
  return getBoolean(googleWorkspace?.suspended) === true || getBoolean(entraId?.account_enabled) === false;
}

/**
 * Handle InternalActorItem timeline items.
 * 
 * Field mapping:
 * - Title: User name (or user id when name is unavailable)
 * - Line1: User ID / username
 * - Line2: Job title
 * - Line3: Department / organization
 * - Metadata: Manager, office/location, and phone after higher-value org metadata
 * - characterFlags: User characteristics as chips (VIP, Privileged, etc.)
 * - accentText/accentIcon: Highest priority risk indicator
 * - actionButtons: Automatically generated based on available fields
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
  const { googleWorkspace, entraId, ldap } = getInternalActorEnrichments(item);

  const userIdentifier = firstString(
    item.user_id,
    entraId?.sam_account_name,
    entraId?.upn,
    entraId?.email,
    googleWorkspace?.primary_email,
    ldap?.sam_account_name,
    ldap?.upn,
    item.contact_email
  );
  const displayName = firstString(
    item.name,
    googleWorkspace?.display_name,
    entraId?.display_name,
    ldap?.display_name,
    userIdentifier
  );
  const jobTitle = firstString(item.title, googleWorkspace?.job_title, entraId?.job_title, ldap?.job_title);
  const departmentOrOrg = firstString(
    item.org,
    entraId?.department,
    googleWorkspace?.department,
    googleWorkspace?.organization,
    ldap?.department,
    ldap?.company,
    googleWorkspace?.org_unit_path
  );
  const manager = getManagerDisplay(item, entraId, ldap);
  const officeLocation = firstString(entraId?.office, ldap?.office);
  const phone = firstString(item.contact_phone, entraId?.mobile_phone, entraId?.business_phones, ldap?.phone, ldap?.mobile, googleWorkspace?.phone);
  const isDisabled = isInternalActorExplicitlyDisabled(googleWorkspace, entraId);

  // Use the generic characteristics processor
  const { color, accentText, accentIcon, characterFlags } = processCharacteristics(item, {
    characteristics: INTERNAL_ACTOR_CHARACTERISTICS,
    getFields: actor => ({
      is_high_risk: actor.is_high_risk === true,
      is_vip: actor.is_vip === true,
      is_privileged: actor.is_privileged === true,
      is_contractor: actor.is_contractor === true,
      is_service_account: actor.is_service_account === true,
      is_disabled: isDisabled,
    }),
  });

  const metadataItems: CardMetadataItem[] = [
    ...(manager ? [{ key: 'manager', label: 'Manager', value: manager, icon: <Users /> }] : []),
    ...(officeLocation ? [{ key: 'office', label: 'Office / Location', value: officeLocation, icon: <MapPin /> }] : []),
    ...(phone ? [{ key: 'phone', label: 'Phone', value: phone, icon: <Phone /> }] : []),
  ];

  return {
    title: displayName || 'Internal Actor',
    line1: userIdentifier,
    line1Icon: userIdentifier ? <IdCard /> : undefined,
    line2: jobTitle,
    line2Icon: jobTitle ? <Briefcase /> : undefined,
    line3: departmentOrOrg,
    line3Icon: departmentOrOrg ? <Building /> : undefined,
    metadataItems,
    metadataLayout: 'stack',
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
 * - Title: Actor name (most important identifier)
 * - Line1: Organization (if present)
 * - Line2: Contact email (if present)
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
    line1: item.org || undefined,
    line1Icon: item.org ? <Building /> : undefined,
    line2: item.contact_email || undefined,
    line2Icon: item.contact_email ? <Mail /> : undefined,
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
 * - Title: Threat actor name (most important identifier)
 * - Line1: Tag ID (if present)
 * - Line2: Confidence level (if present)
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
    line1: item.tag_id || undefined,
    line1Icon: item.tag_id ? <Tag /> : undefined,
    line2: item.confidence ? `Confidence: ${item.confidence}%` : undefined,
    line2Icon: item.confidence ? <Percent /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
