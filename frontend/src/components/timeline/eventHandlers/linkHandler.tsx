import type { TimelineItem } from '@/types/timeline';
import type { LinkItem } from '@/types/generated/models/LinkItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { ExternalLink } from 'lucide-react';

export function isLinkItem(item: TimelineItem): item is TimelineItem & LinkItem {
  return item.type === 'link';
}

export function handleLinkItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isLinkItem(item)) {
    throw new Error('Item is not a LinkItem');
  }

  const Icon = getTimelineIcon('link');

  const urlDisplay = item.url && item.url.length > 50
    ? item.url.substring(0, 50) + '...'
    : item.url;

  return {
    title: urlDisplay || 'Link',
    line1: item.url ? (
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="hover:underline"
      >
        Open in new tab
      </a>
    ) : undefined,
    line1Icon: item.url ? <ExternalLink /> : undefined,
    disableCopyTargets: ['line1'],
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
