import { GitFork, Monitor } from 'lucide-react';
import { isProcessTreeItem, type TimelineItem } from '@/types/timeline';
import { ProcessTreeSnapshot } from '../ProcessTreeSnapshot';
import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

export function handleProcessTreeItem(item: TimelineItem, options: CardFactoryOptions): CardConfig {
  if (!isProcessTreeItem(item)) {
    throw new Error('Item is not a ProcessTreeItem');
  }

  const count = item.processes.length;
  const malicious = item.processes.filter((process) => process.verdict === 'malicious').length;
  const summary = `${count} ${count === 1 ? 'process' : 'processes'}`;
  return {
    title: 'Process Tree',
    line1: item.hostname || undefined,
    line1Icon: item.hostname ? <Monitor /> : undefined,
    line2: malicious ? `${summary} · ${malicious} malicious` : summary,
    baseIcon: <GitFork />,
    system: 'default',
    size: options.size || 'x-large',
    actionButtons: options.actionButtons,
    children: options.variant === 'super-compact' ? undefined : (
      <ProcessTreeSnapshot processes={item.processes} hostname={item.hostname} timestamp={item.timestamp} />
    ),
    _item: item,
  };
}
