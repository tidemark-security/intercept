import type { TimelineItem } from '@/types/timeline';
import type { ForensicArtifactItem } from '@/types/generated/models/ForensicArtifactItem';
import { getTimelineIcon } from '@/utils/timelineIcons';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { FileText, Fingerprint, Link } from 'lucide-react';

export function isForensicArtifactItem(item: TimelineItem): item is ForensicArtifactItem {
  return item.type === 'forensic_artifact';
}

export function handleForensicArtifactItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isForensicArtifactItem(item)) {
    throw new Error('Item is not a ForensicArtifactItem');
  }

  const Icon = getTimelineIcon('forensic_artifact');

  return {
    title: item.hash ? `${item.hash}` : 'Forensic Artifact',
    line1: item.hash ? `${item.hash.substring(0, 32)}...` : 'Forensic Artifact',
    line1Icon: <Fingerprint />,
    line2: item.url || undefined,
    line2Icon: item.url ? <Link /> : undefined,
    line3: item.description || undefined,
    line3Icon: item.description ? <FileText /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
