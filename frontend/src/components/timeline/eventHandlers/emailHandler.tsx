import type { TimelineItem } from '@/types/timeline';
import type { EmailItem } from '@/types/generated/models/EmailItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { Hash, Mail, User } from 'lucide-react';

export function isEmailItem(item: TimelineItem): item is EmailItem {
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
    line1: item.subject || 'No Subject',
    line1Icon: <Mail />,
    line2: item.sender || undefined,
    line2Icon: item.sender ? <User /> : undefined,
    line3: item.recipient || undefined,
    line3Icon: item.recipient ? <Mail /> : undefined,
    line4: item.message_id || undefined,
    line4Icon: item.message_id ? <Hash /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
