import type { TimelineItem } from '@/types/timeline';
import type { AlertItem } from '@/types/generated/models/AlertItem';
import { getTimelineIcon } from '@/utils/timelineIcons';
import { convertNumericToAlertId } from '@/utils/caseHelpers';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { AlertCircle, ChevronsUp, Hash, User } from 'lucide-react';

export function isAlertItem(item: TimelineItem): item is TimelineItem & AlertItem {
  return item.type === 'alert';
}

export function handleAlertItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isAlertItem(item)) {
    throw new Error('Item is not an AlertItem');
  }

  const Icon = getTimelineIcon('alert');
  const titleValue =
    typeof item.alert_id === 'number'
      ? convertNumericToAlertId(item.alert_id)
      : item.alert_id;

  return {
    title: titleValue ? `${titleValue}` : 'Alert',
    line1: item.title || 'Alert',
    line1Icon: <AlertCircle />,
    line2: item.alert_id?.toString() || undefined,
    line2Icon: item.alert_id ? <Hash /> : undefined,
    line3: item.priority?.toUpperCase() || undefined,
    line3Icon: item.priority ? <ChevronsUp /> : undefined,
    line4: item.assignee || undefined,
    line4Icon: item.assignee ? <User /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
