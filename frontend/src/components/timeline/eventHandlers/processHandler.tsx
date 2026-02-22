import type { TimelineItem } from '@/types/timeline';
import type { ProcessItem } from '@/types/generated/models/ProcessItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { Cpu, Hash, Terminal, User } from 'lucide-react';

export function isProcessItem(item: TimelineItem): item is ProcessItem {
  return item.type === 'process';
}

export function handleProcessItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isProcessItem(item)) {
    throw new Error('Item is not a ProcessItem');
  }

  const Icon = getTimelineIcon('process');

  const cmdDisplay = item.command_line && item.command_line.length > 60
    ? item.command_line.substring(0, 60) + '...'
    : item.command_line;

  return {
    title: item.process_name ? `${item.process_name}` : 'Process',
    line1: item.process_name || 'Process',
    line1Icon: <Cpu />,
    line2: item.process_id ? `PID: ${item.process_id}` : undefined,
    line2Icon: item.process_id ? <Hash /> : undefined,
    line3: cmdDisplay,
    line3Icon: cmdDisplay ? <Terminal /> : undefined,
    line4: item.user_account ? `User: ${item.user_account}` : undefined,
    line4Icon: item.user_account ? <User /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
