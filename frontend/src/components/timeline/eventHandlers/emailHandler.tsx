import type { TimelineItem } from '@/types/timeline';
import type { EmailItem } from '@/types/generated/models/EmailItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { Hash, Mail, User } from 'lucide-react';

export function isEmailItem(item: TimelineItem): item is TimelineItem & EmailItem {
  return item.type === 'email';
}

export function handleEmailItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isEmailItem(item)) {
    throw new Error('Item is not an EmailItem');
  }

  const Icon = getTimelineIcon('email');

  return {
    title: item.subject ? `${item.subject}` : 'Email',
    line1: item.sender || undefined,
    line1Icon: item.sender ? <User /> : undefined,
    line2: item.recipient || undefined,
    line2Icon: item.recipient ? <Mail /> : undefined,
    line3: item.message_id || undefined,
    line3Icon: item.message_id ? <Hash /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
