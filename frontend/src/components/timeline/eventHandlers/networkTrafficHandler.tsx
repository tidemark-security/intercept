import type { TimelineItem } from '@/types/timeline';
import type { NetworkTrafficItem } from '@/types/generated/models/NetworkTrafficItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { ArrowRight, Network } from 'lucide-react';

export function isNetworkTrafficItem(item: TimelineItem): item is TimelineItem & NetworkTrafficItem {
  return item.type === 'network_traffic';
}

function formatBytes(bytes: number | undefined | null): string | undefined {
  if (bytes === undefined || bytes === null) return undefined;

  const sizes = ['B', 'KB', 'MB', 'GB'];
  if (bytes === 0) return '0 B';

  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const size = bytes / Math.pow(1024, i);

  return `${size.toFixed(2)} ${sizes[i]}`;
}

export function handleNetworkTrafficItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isNetworkTrafficItem(item)) {
    throw new Error('Item is not a NetworkTrafficItem');
  }

  const Icon = getTimelineIcon('network_traffic');

  const connection = item.source_ip && item.destination_ip
    ? `${item.source_ip} → ${item.destination_ip}`
    : undefined;

  const bytesDisplay = formatBytes(item.bytes_sent);

  return {
    title: item.destination_ip ? `${item.destination_ip}` : 'Network Traffic',
    line1: connection || 'Network Traffic',
    line1Icon: <Network />,
    line2: item.protocol ? `Protocol: ${item.protocol}` : undefined,
    line2Icon: item.protocol ? <Network /> : undefined,
    line3: bytesDisplay ? `Sent: ${bytesDisplay}` : undefined,
    line3Icon: bytesDisplay ? <ArrowRight /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
