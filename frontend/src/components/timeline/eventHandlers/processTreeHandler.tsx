import { GitFork } from 'lucide-react';
import { isProcessTreeItem, type TimelineItem } from '@/types/timeline';
import { ProcessTreeSnapshot } from '../ProcessTreeSnapshot';
import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

export function handleProcessTreeItem(item: TimelineItem, options: CardFactoryOptions): CardConfig {
  if (!isProcessTreeItem(item)) {
    throw new Error('Item is not a ProcessTreeItem');
  }

  const count = item.processes.length;
  return {
    title: 'Process Tree',
    line1: item.hostname || undefined,
    line2: `${count} ${count === 1 ? 'process' : 'processes'}`,
    baseIcon: <GitFork />,
    system: 'default',
    size: options.size || 'x-large',
    actionButtons: options.actionButtons,
    children: options.variant === 'super-compact' ? undefined : (
      <ProcessTreeSnapshot processes={item.processes} timestamp={item.timestamp} />
    ),
    _item: item,
  };
}
