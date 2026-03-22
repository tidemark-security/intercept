/**
 * Task Item Handler
 * 
 * Handler for TaskItem timeline items.
 * Tasks display status, assignee, and due date information.
 */

import React from 'react';
import type { TimelineItem } from '@/types/timeline';
import type { TaskItem } from '@/types/generated/models/TaskItem';
import { getTimelineIcon } from '@/utils/timelineIcons';
import { formatAbsoluteTime } from '@/utils/dateFormatters';

import { Badge } from '@/components/data-display/Badge';
import type { CardConfig, CardFactoryOptions, ItemCharacteristic } from '../TimelineCardFactory';
import { processCharacteristics } from '../TimelineCardFactory';

import { Calendar, Check, CheckCircle, ChevronUp, ChevronsUp, Hash, User } from 'lucide-react';
/**
 * Check if item is a TaskItem
 */
export function isTaskItem(item: TimelineItem): item is TimelineItem & TaskItem {
  return item.type === 'task';
}

/**
 * Task characteristic definitions
 * Priority determines which characteristic takes precedence for accent display
 */
const TASK_CHARACTERISTICS: Record<string, ItemCharacteristic> = {
  is_completed: {
    priority: 1,
    color: 'success',
    accentText: 'Completed',
    accentIcon: <Check />,
    badgeIcon: <Check />,
    badgeText: 'Completed',
  },
  is_overdue: {
    priority: 2,
    color: 'error',
    accentText: 'Overdue',
    accentIcon: <ChevronsUp />,
    badgeIcon: <ChevronsUp />,
    badgeText: 'Overdue',
  },
  is_due_soon: {
    priority: 3,
    color: 'warning',
    accentText: 'Due Soon',
    accentIcon: <ChevronUp />,
    badgeIcon: <ChevronUp />,
    badgeText: 'Due Soon',
  },
};

/**
 * Calculate task characteristics based on due date and status
 */
function getTaskCharacteristics(item: TaskItem): Partial<TaskItem> & Record<string, boolean> {
  const characteristics: Record<string, boolean> = {
    is_completed: false,
    is_overdue: false,
    is_due_soon: false,
  };

  // Check completed status (API returns UPPERCASE TaskStatus values)
  if (item.status === 'DONE') {
    characteristics.is_completed = true;
    return characteristics;
  }

  // Check due date for overdue/due soon
  if (item.due_date) {
    const dueDate = new Date(item.due_date);
    const now = new Date();
    const oneDayFromNow = new Date(now.getTime() + 24 * 60 * 60 * 1000);

    if (dueDate < now) {
      characteristics.is_overdue = true;
    } else if (dueDate <= oneDayFromNow) {
      characteristics.is_due_soon = true;
    }
  }

  return characteristics;
}

function formatLabel(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  return value
    .split('_')
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
}

/**
 * Handle TaskItem timeline items.
 * 
 * Field mapping:
 * - Line1: Task description (most important)
 * - Line2: Status
 * - Line3: Assignee (if present)
 * - Line4: Due date (if present)
 * - characterFlags: Task status badges (Completed, Overdue, Due Soon)
 * - accentText/accentIcon: Highest priority status indicator
 * - Icon: FeatherCheckSquare
 * - Color: Based on task characteristics (overdue/due soon/completed)
 */
export function handleTaskItem(
  item: TimelineItem,
  options: CardFactoryOptions
): CardConfig {
  if (!isTaskItem(item)) {
    throw new Error('Item is not a TaskItem');
  }

  const Icon = getTimelineIcon('task');
  const IconComponent = Icon ? <Icon /> : undefined;

  // Calculate task characteristics and process them
  const itemWithCharacteristics = { ...item, ...getTaskCharacteristics(item) };
  const { color, accentText, accentIcon, characterFlags } = processCharacteristics(
    itemWithCharacteristics,
    { characteristics: TASK_CHARACTERISTICS }
  );

  // Format status for display
  const statusDisplay = formatLabel(item.status) || 'To Do';
  const priorityDisplay = formatLabel(item.priority);

  const metaParts: string[] = [];
  if (item.task_human_id) {
    metaParts.push(item.task_human_id);
  }
  if (statusDisplay) {
    metaParts.push(`Status: ${statusDisplay}`);
  }
  if (priorityDisplay) {
    metaParts.push(`Priority: ${priorityDisplay}`);
  }

  const metaLine = metaParts.length > 0 ? metaParts.join(' • ') : undefined;
  const metaIcon = metaLine
    ? item.task_human_id
      ? <Hash />
      : <CheckCircle />
    : undefined;

  return {
    title: item.task_human_id ? `${item.task_human_id}` : 'Task',
    line1: item.title || item.description || 'Untitled Task',
    line1Icon: <CheckCircle />,
    line2: metaLine,
    line2Icon: metaIcon,
    line3: item.assignee ? `Assignee: ${item.assignee}` : undefined,
    line3Icon: item.assignee ? <User /> : undefined,
    line4: item.due_date
      ? `Due: ${formatAbsoluteTime(item.due_date, 'MMM d, yyyy')}`
      : undefined,
    line4Icon: item.due_date ? <Calendar /> : undefined,
    characterFlags,
    accentText,
    accentIcon,
    baseIcon: IconComponent,
    system: color,
    size: options.size || 'large',
    actionButtons: options.actionButtons,
    _item: item,
  };
}
