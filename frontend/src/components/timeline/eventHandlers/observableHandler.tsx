/**
 * Observable Item Handler
 * 
 * Handler for ObservableItem timeline items (IOCs).
 * Observables display type and value information.
 */

import type { TimelineItem } from '@/types/timeline';
import type { ObservableItem } from '@/types/generated/models/ObservableItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { FileText, Fingerprint } from 'lucide-react';
/**
 * Check if item is an ObservableItem
 */
export function isObservableItem(item: TimelineItem): item is ObservableItem {
  return item.type === 'observable';
}

/**
 * Format observable type for display
 */
function formatObservableType(type: string | undefined | null): string {
  if (!type) return 'Unknown';
  return type.replace(/_/g, ' ').toUpperCase();
}

/**
 * Handle ObservableItem timeline items.
 * 
 * Field mapping:
 * - Line1: Observable value (most important - the actual IOC)
 * - Line2: Observable type (IP, Domain, Hash, etc.)
 * - Line3: Description (if present)
 * - Icon: Fingerprint
 * - Color: default (observables are neutral evidence)
 */
export function handleObservableItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isObservableItem(item)) {
    throw new Error('Item is not an ObservableItem');
  }

  const Icon = getTimelineIcon('observable');
  const typeDisplay = formatObservableType(item.observable_type);
  const IconComponent = Icon ? <Icon /> : undefined;

  return {
    title: item.observable_value ? `${item.observable_value}` : 'Observable',
    line1: item.observable_value || 'No value provided',
    line1Icon: <Fingerprint />,
    line2: typeDisplay,
    line2Icon: <FileText />,
    line3: item.description || undefined,
    line3Icon: item.description ? <FileText /> : undefined,
    baseIcon: IconComponent,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
