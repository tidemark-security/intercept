/**
 * System Item Handler
 * 
 * Handler for SystemItem timeline items.
 * Systems display hostname, IP, and risk indicators.
 */

import React from 'react';
import type { TimelineItem } from '@/types/timeline';
import type { SystemItem } from '@/types/generated/models/SystemItem';
import { getSystemTypeIcon, getSystemTypeLabel } from '@/utils/systemTypeIcons';

import { Badge } from '@/components/data-display/Badge';
import type { CardConfig, CardFactoryOptions, CardSystem, ItemCharacteristic } from '../TimelineCardFactory';
import { processCharacteristics } from '../TimelineCardFactory';

import { Biohazard, ChevronsUp, Cpu, Factory, Globe, Key } from 'lucide-react';
/**
 * Check if item is a SystemItem
 */
export function isSystemItem(item: TimelineItem): item is TimelineItem & SystemItem {
  return item.type === 'system';
}

/**
 * System characteristic definitions
 * Higher priority characteristics take precedence for accent display
 */
const SYSTEM_CHARACTERISTICS: Record<string, ItemCharacteristic> = {
  is_critical: {
    priority: 1,
    color: 'error',
    accentText: 'Critical',
    accentIcon: <ChevronsUp />,
    badgeIcon: <ChevronsUp />,
    badgeText: 'Critical',
  },
  is_privileged: {
    priority: 2,
    color: 'error',
    accentText: 'Privileged',
    accentIcon: <Key />,
    badgeIcon: <Key />,
    badgeText: 'Privileged',
  },
  is_high_risk: {
    priority: 3,
    color: 'error',
    accentText: 'High Risk',
    accentIcon: <Biohazard />,
    badgeIcon: <Biohazard />,
    badgeText: 'High Risk',
  },
  is_internet_facing: {
    priority: 4,
    color: 'warning',
    accentText: 'Internet Facing',
    accentIcon: <Globe />,
    badgeIcon: <Globe />,
    badgeText: 'Internet Facing',
  },
  is_legacy: {
    priority: 5,
    color: 'warning',
    accentText: 'Legacy',
    accentIcon: <Factory />,
    badgeIcon: <Factory />,
    badgeText: 'Legacy',
  },
};

/**
 * Handle SystemItem timeline items.
 * 
 * Field mapping:
 * - Line1: Hostname (most important identifier)
 * - Line2: IP Address
 * - Line3: System type (if present)
 * - characterFlags: System characteristics as chips (Critical, High Risk, etc.)
 * - accentText/accentIcon: Highest priority risk indicator
 * - Icon: Cpu
 * - Color: Based on highest priority risk indicator
 */
export function handleSystemItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isSystemItem(item)) {
    throw new Error('Item is not a SystemItem');
  }

  const Icon = getSystemTypeIcon(item.system_type);
  const IconComponent = <Icon />;

  // Use the generic characteristics processor
  const { color, accentText, accentIcon, characterFlags } = processCharacteristics(item, {
    characteristics: SYSTEM_CHARACTERISTICS,
  });

  return {
    title: item.hostname || 'Unknown System',
    line2: getSystemTypeLabel(item.system_type),
    line2Icon: <Icon />,
    line1: item.ip_address || undefined,
    line1Icon: item.ip_address ? <Globe /> : undefined,
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


