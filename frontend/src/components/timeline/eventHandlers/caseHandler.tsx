import type { TimelineItem } from '@/types/timeline';
import type { CaseItem } from '@/types/generated/models/CaseItem';
import { getTimelineIcon } from '@/utils/timelineIcons';
import { convertNumericToHumanId } from '@/utils/caseHelpers';

import type { CardConfig, CardFactoryOptions } from '../TimelineCardFactory';

import { Briefcase, ChevronsUp, Hash, User } from 'lucide-react';

export function isCaseItem(item: TimelineItem): item is CaseItem {
  return item.type === 'case';
}

export function handleCaseItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isCaseItem(item)) {
    throw new Error('Item is not a CaseItem');
  }

  const Icon = getTimelineIcon('case');
  const titleValue =
    typeof item.case_id === 'number'
      ? convertNumericToHumanId(item.case_id)
      : item.case_id;

  return {
    title: titleValue ? `${titleValue}` : 'Case',
    line1: item.title || 'Case',
    line1Icon: <Briefcase />,
    line2: item.case_id ? `Case ID: ${item.case_id}` : undefined,
    line2Icon: item.case_id ? <Hash /> : undefined,
    line3: item.priority ? `Priority: ${item.priority.toUpperCase()}` : undefined,
    line3Icon: item.priority ? <ChevronsUp /> : undefined,
    line4: item.assignee ? `Assigned to: ${item.assignee}` : undefined,
    line4Icon: item.assignee ? <User /> : undefined,
    baseIcon: Icon ? <Icon /> : undefined,
    system: 'default',
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
