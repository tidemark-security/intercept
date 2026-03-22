import type { TimelineItem } from '@/types/timeline';
import type { RegistryChangeItem } from '@/types/generated/models/RegistryChangeItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { Database, Edit } from 'lucide-react';

export function isRegistryChangeItem(item: TimelineItem): item is TimelineItem & RegistryChangeItem {
  return item.type === 'registry_change';
}

export function handleRegistryChangeItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isRegistryChangeItem(item)) {
    throw new Error('Item is not a RegistryChangeItem');
  }

  const Icon = getTimelineIcon('registry_change');

  const operation = item.operation
    ? item.operation.toUpperCase()
    : 'MODIFIED';

  return {
    title: item.registry_key ? `${item.registry_key}` : 'Registry Change',
    line1: item.registry_value ? `Value: ${item.registry_value}` : undefined,
    line1Icon: item.registry_value ? <Edit /> : undefined,
    line2: `Operation: ${operation}`,
    line2Icon: <Edit />,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
