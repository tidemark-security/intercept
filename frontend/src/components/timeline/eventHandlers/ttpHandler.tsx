/**
 * TTP Item Handler
 * 
 * Handler for TTPItem (Tactics, Techniques, and Procedures) timeline items.
 * TTPs display MITRE ATT&CK framework information.
 */

import type { TimelineItem } from '@/types/timeline';
import type { TTPItem } from '@/types/generated/models/TTPItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { Crosshair, FileText } from 'lucide-react';
/**
 * Check if item is a TTPItem
 */
export function isTTPItem(item: TimelineItem): item is TTPItem {
  return item.type === 'ttp';
}

/**
 * Handle TTPItem timeline items.
 * 
 * Field mapping:
 * - Line1: Tactic (e.g., "Execution")
 * - Line2: MITRE ATT&CK description (official technique description)
 * - Line3: User notes (if present)
 * - Icon: FeatherTarget
 * - Color: default (TTPs are neutral threat intelligence)
 */
export function handleTTPItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isTTPItem(item)) {
    throw new Error('Item is not a TTPItem');
  }

  const Icon = getTimelineIcon('ttp');
  const IconComponent = Icon ? <Icon /> : undefined;

  const mitreId = item.mitre_id;
  const ttpTitle = item.title;
  const cardTitle = mitreId && ttpTitle
    ? `${mitreId}: ${ttpTitle}`
    : mitreId
      ? mitreId
      : ttpTitle
        ? ttpTitle
        : 'TTP';

  return {
    title: cardTitle,
    line1: item.tactic || undefined,
    line1Icon: item.tactic ? <Crosshair /> : undefined,
    line2: item.mitre_description || undefined,
    line2Icon: item.mitre_description ? <FileText /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
