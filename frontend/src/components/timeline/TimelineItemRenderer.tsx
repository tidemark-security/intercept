import React, { useState } from 'react';
import { useTheme } from '@/contexts/ThemeContext';
import { Link } from '@/components/navigation/Link';
import { ActivityItem } from '@/components/data-display/ActivityItem';
import { BaseCard } from '@/components/cards/BaseCard';
import { AlertCard } from '@/components/timeline/AlertCard';
import { AlertCardContent } from '@/components/timeline/AlertCardContent';
import { TaskCardContent } from '@/components/timeline/TaskCardContent';
import { CaseCardContent } from '@/components/timeline/CaseCardContent';
import MarkdownContent from '@/components/data-display/MarkdownContent';
import { createTimelineCard } from '@/components/timeline/TimelineCardFactory';
import type { TimelineItem } from '@/types/timeline';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import type { TaskStatus } from '@/types/generated/models/TaskStatus';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { CaseStatus } from '@/types/generated/models/CaseStatus';
import type { LinkTemplate } from '@/utils/linkTemplates';
import {
  getTimelineItemIcon,
  getTimelineItemAction,
  getTimelineItemLabel,
} from '@/utils/timelineMapping';
import { isAlertItem, isNoteItem, isTaskItem } from '@/types/timeline';
import type { CaseItem } from '@/types/generated/models/CaseItem';
import { convertNumericToAlertId, convertNumericToHumanId } from '@/utils/caseHelpers';

import { Button } from '@/components/buttons/Button';

import { ChevronDown, ChevronRight } from 'lucide-react';
/**
 * Type guard for CaseItem
 */
function isCaseItem(item: TimelineItem): item is CaseItem {
  return item.type === 'case';
}

/**
 * Get the detail page href for linkable timeline items (alert, case, task).
 * Returns null for items that don't have detail pages.
 */
function getItemDetailHref(item: TimelineItem): string | null {
  if (isAlertItem(item) && item.alert_id) {
    return `/alerts/${convertNumericToAlertId(item.alert_id)}`;
  }
  if (isCaseItem(item) && item.case_id) {
    return `/cases/${convertNumericToHumanId(item.case_id)}`;
  }
  if (isTaskItem(item)) {
    // TaskItem has task_human_id directly
    const taskItem = item as TimelineItem & { task_human_id?: string | null };
    if (taskItem.task_human_id) {
      return `/tasks/${taskItem.task_human_id}`;
    }
  }
  return null;
}

function hasText(value: string | null | undefined): value is string {
  return !!value && value.trim().length > 0;
}

function isLinkedTimelineType(type: TimelineItem['type'] | undefined): boolean {
  return type === 'alert' || type === 'case' || type === 'task';
}

function flattenReplies(items: TimelineItem[]): TimelineItem[] {
  const flattened: TimelineItem[] = [];

  const traverse = (currentItems: TimelineItem[]) => {
    for (const currentItem of currentItems) {
      flattened.push(currentItem);
      const nestedReplies = currentItem.replies as TimelineItem[] | null | undefined;
      if (nestedReplies && Array.isArray(nestedReplies) && nestedReplies.length > 0) {
        traverse(nestedReplies);
      }
    }
  };

  traverse(items);
  return flattened;
}

function collectItemIds(items: TimelineItem[], targetSet: Set<string>): void {
  for (const currentItem of items) {
    if (currentItem.id) {
      targetSet.add(currentItem.id);
    }

    const nestedReplies = currentItem.replies as TimelineItem[] | null | undefined;
    if (nestedReplies && Array.isArray(nestedReplies) && nestedReplies.length > 0) {
      collectItemIds(nestedReplies, targetSet);
    }
  }
}

function clearCardLines(
  cardConfig: ReturnType<typeof createTimelineCard>,
  options: { clearCharacterFlags?: boolean } = {}
) {
  cardConfig.line1 = undefined;
  cardConfig.line1Icon = undefined;
  cardConfig.line2 = undefined;
  cardConfig.line2Icon = undefined;
  cardConfig.line3 = undefined;
  cardConfig.line3Icon = undefined;
  cardConfig.line4 = undefined;
  cardConfig.line4Icon = undefined;

  if (options.clearCharacterFlags) {
    cardConfig.characterFlags = undefined;
  }
}

function buildEntityTitle(
  identifier: string,
  title: string | null | undefined,
  isDarkTheme: boolean
): React.ReactNode {
  return (
    <div className="flex flex-col gap-0.5">
      <span>{identifier}</span>
      {title && (
        <span className={isDarkTheme ? 'text-body font-body text-brand-primary' : 'text-body font-body text-black'}>
          {title}
        </span>
      )}
    </div>
  );
}

function getSourceEntityLabel(item: TimelineItem): 'alert' | 'task' | 'case' {
  if (isAlertItem(item)) {
    return 'alert';
  }
  if (isTaskItem(item)) {
    return 'task';
  }
  return 'case';
}

/**
 * Props for TimelineItemRenderer component
 */
export interface TimelineItemRendererProps {
  /** Timeline item to render (primary item when multiple items are grouped) */
  item: TimelineItem;
  
  /** All items in this group (for collapsed/grouped rendering). If provided, multiple cards will be rendered. */
  items?: TimelineItem[];
  
  /** Index of this item in the parent array */
  index: number;
  
  /** Total number of items in the parent array */
  total: number;
  
  /** Current nesting depth (0 = top level, 1+ = nested replies) */
  depth?: number;
  
  /** Entity ID (alert ID, case ID, or task ID) for card context */
  entityId: number | null;
  
  /** Entity type (alert, case, or task) for card context */
  entityType?: 'alert' | 'case' | 'task';
  
  // Interaction handlers
  
  /** Handler for flagging/unflagging a timeline item */
  onFlag?: (itemId: string) => void;
  
  /** Handler for highlighting/unhighlighting a timeline item */
  onHighlight?: (itemId: string) => void;
  
  /** Handler for editing a timeline item */
  onEdit?: (itemId: string) => void;
  
  /** Handler for deleting a timeline item */
  onDelete?: (itemId: string) => void;
  
  /** Handler for batch deleting multiple timeline items (used for grouped items) */
  onDeleteBatch?: (itemIds: string[]) => void;
  
  /** Handler for replying to a timeline item */
  onReply?: (itemId: string) => void;
  
  /** Sort field to determine which timestamp to display */
  sortBy?: 'created_at' | 'timestamp';
  
  /** Link templates from API for auto-generating link buttons */
  linkTemplates?: LinkTemplate[];
}

/**
 * TimelineItemRenderer - Renders a single timeline item with recursive reply support
 * 
 * This component encapsulates the complex logic of rendering timeline items:
 * - Determines appropriate icon, action, timestamp based on item type
 * - Renders all item descriptions as markdown (consistent with notes)
 * - For non-note items, displays cards below the markdown description
 * - Supports grouped items: when multiple items share timestamp/description, renders multiple cards
 * - Recursively renders nested replies
 * - Handles read-only vs editable states
 * - Manages reply enablement (only on top-level notes and last reply)
 * 
 * Extracted from AlertTimeline.tsx as the authoritative implementation.
 * 
 * @example
 * ```tsx
 * // Single item rendering
 * {timelineItems.map((item, index) => (
 *   <TimelineItemRenderer
 *     key={item.id}
 *     item={item}
 *     index={index}
 *     total={timelineItems.length}
 *     entityId={alertId}
 *     onFlag={handleFlagItem}
 *     onHighlight={handleHighlightItem}
 *     onEdit={handleEditItem}
 *     onDelete={handleDeleteItem}
 *   />
 * ))}
 * 
 * // Grouped items rendering
 * {groupedItems.map((group, index) => (
 *   <TimelineItemRenderer
 *     key={group.item.id}
 *     item={group.item}
 *     items={group.items}
 *     index={group.index}
 *     total={timelineItems.length}
 *     entityId={alertId}
 *   />
 * ))}
 * ```
 */
export function TimelineItemRenderer({
  item,
  items,
  index,
  total,
  depth = 0,
  entityId,
  entityType,
  onFlag,
  onHighlight,
  onEdit,
  onDelete,
  onDeleteBatch,
  onReply,
  sortBy = 'created_at',
  linkTemplates,
}: TimelineItemRendererProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';

  // State for collapsing/expanding source timeline items from linked alerts/tasks
  const [sourceItemsExpanded, setSourceItemsExpanded] = useState(false);
  // State for hover on source toggle area
  const [isSourceToggleHovered, setIsSourceToggleHovered] = useState(false);
  
  const Icon = getTimelineItemIcon(item.type || 'note');
  const action = `${getTimelineItemAction(item.type || 'note')} ${getTimelineItemLabel(item.type || 'note')}`;

  // Determine username based on item type
  const username = item.created_by || 'System';

  // Determine variant based on item type
  const variant = item.type === 'alert' || !item.created_by ? 'primary' : undefined;

  // Check if this is a linked item type (alerts, cases, tasks are always injected from linked entities)
  const isLinkedItemType = isLinkedTimelineType(item.type);

  // Determine if read-only:
  // 1. Linked item types (alert, case, task) are always read-only (belong to linked entities)
  // 2. System items are read-only (no created_by)
  // 3. If no action handlers are passed, treat as read-only (preview/readonly mode)
  const hasActionHandlers = !!(onFlag || onHighlight || onEdit || onDelete);
  const readOnly = isLinkedItemType || !item.created_by || !hasActionHandlers;

  // Use items prop if provided (grouped items), otherwise single item
  const itemsToRender = items && items.length > 1 ? items : [item];
  const isGrouped = itemsToRender.length > 1;
  
  // Collect all item IDs for group-level actions
  const groupItemIds = isGrouped ? itemsToRender.map(i => i.id || '').filter(Boolean) : [];

  const renderTopLevelCard = (currentItem: TimelineItem, cardIndex: number): React.ReactNode => {
    const timelineCurrentItem = currentItem as TimelineItem;
    const itemKey = timelineCurrentItem.id || `item-${cardIndex}`;

    if ((timelineCurrentItem as any).type === 'note') {
      return null;
    }

    const isCurrentItemLinked = isLinkedTimelineType(timelineCurrentItem.type);
    const cardConfig = createTimelineCard(timelineCurrentItem, {
      size: 'x-large',
      alertId: entityId,
      entityType,
      enableActionMenu: isGrouped,
      itemId: timelineCurrentItem.id,
      onFlag,
      onHighlight,
      onDelete,
      onEdit,
      readOnly: isCurrentItemLinked || !item.created_by,
      linkTemplates,
    });

    if (isGrouped) {
      cardConfig.className = `${cardConfig.className || ''} flex-1${isCurrentItemLinked ? ' min-w-40' : ''}`;
    }

    const description = timelineCurrentItem.description;
    const descriptionNode = hasText(description) ? <MarkdownContent content={description} /> : null;

    let children: React.ReactNode = descriptionNode;

    if (isAlertItem(timelineCurrentItem)) {
      cardConfig.size = 'x-large';
      const alertId = timelineCurrentItem.alert_id ? convertNumericToAlertId(timelineCurrentItem.alert_id) : 'Alert';
      cardConfig.title = buildEntityTitle(alertId, timelineCurrentItem.title, isDarkTheme);
      clearCardLines(cardConfig);

      const alertData: Partial<AlertRead> & { title: string } = {
        id: timelineCurrentItem.alert_id || 0,
        human_id: timelineCurrentItem.alert_id ? convertNumericToAlertId(timelineCurrentItem.alert_id) : undefined,
        title:
          timelineCurrentItem.title ||
          (timelineCurrentItem.alert_id ? convertNumericToAlertId(timelineCurrentItem.alert_id) : 'Alert'),
        description: timelineCurrentItem.description,
        priority: timelineCurrentItem.priority,
        status: ((timelineCurrentItem as TimelineItem & { status?: AlertStatus | null }).status ?? 'NEW') as AlertStatus,
        created_at: timelineCurrentItem.created_at || '',
        updated_at:
          (timelineCurrentItem as TimelineItem & { updated_at?: string }).updated_at ||
          timelineCurrentItem.created_at ||
          '',
        assignee: timelineCurrentItem.assignee,
        tags: timelineCurrentItem.tags,
        source: (timelineCurrentItem as TimelineItem & { source?: string }).source,
        case_id: (timelineCurrentItem as TimelineItem & { case_id?: number }).case_id,
      };

      children = (
        <div className="w-full pt-2 flex flex-col gap-3">
          <AlertCardContent data={alertData} />
        </div>
      );
    } else if (isTaskItem(timelineCurrentItem)) {
      cardConfig.size = 'x-large';
      const taskId = timelineCurrentItem.task_human_id || 'Task';
      cardConfig.title = buildEntityTitle(taskId, timelineCurrentItem.title, isDarkTheme);
      clearCardLines(cardConfig, { clearCharacterFlags: true });

      const taskData: Partial<TaskRead> & { title: string } = {
        id: timelineCurrentItem.task_id || 0,
        human_id: timelineCurrentItem.task_human_id || '',
        title: timelineCurrentItem.title || (timelineCurrentItem.task_human_id || 'Task'),
        description: timelineCurrentItem.description,
        priority: timelineCurrentItem.priority ?? undefined,
        status: (timelineCurrentItem.status || 'OPEN') as TaskStatus,
        created_at: timelineCurrentItem.created_at || '',
        updated_at:
          (timelineCurrentItem as TimelineItem & { updated_at?: string }).updated_at ||
          timelineCurrentItem.created_at ||
          '',
        assignee: timelineCurrentItem.assignee,
        tags: timelineCurrentItem.tags,
        due_date: timelineCurrentItem.due_date,
        created_by: timelineCurrentItem.created_by || 'System',
        case_id: (timelineCurrentItem as TimelineItem & { case_id?: number }).case_id,
      };

      children = (
        <div className="w-full pt-2 flex flex-col gap-3">
          <TaskCardContent data={taskData} />
        </div>
      );
    } else if (isCaseItem(timelineCurrentItem)) {
      cardConfig.size = 'x-large';
      const caseHumanId = convertNumericToHumanId(timelineCurrentItem.case_id);
      cardConfig.title = buildEntityTitle(caseHumanId, timelineCurrentItem.title, isDarkTheme);
      clearCardLines(cardConfig);

      const caseData: Partial<CaseRead> & { title: string } = {
        id: timelineCurrentItem.case_id,
        human_id: caseHumanId,
        title: timelineCurrentItem.title || caseHumanId,
        description: timelineCurrentItem.description,
        priority: timelineCurrentItem.priority ?? undefined,
        status: ((timelineCurrentItem as TimelineItem & { status?: CaseStatus | null }).status ?? 'NEW') as CaseStatus,
        created_at: timelineCurrentItem.created_at || '',
        updated_at:
          (timelineCurrentItem as TimelineItem & { updated_at?: string }).updated_at ||
          timelineCurrentItem.created_at ||
          '',
        assignee: timelineCurrentItem.assignee,
        tags: timelineCurrentItem.tags,
        created_by: timelineCurrentItem.created_by || 'System',
      };

      children = (
        <div className="w-full pt-2 flex flex-col gap-3">
          <CaseCardContent data={caseData} />
        </div>
      );
    }

    const baseCardElement = (
      <BaseCard key={itemKey} {...cardConfig}>
        {children}
      </BaseCard>
    );

    const itemHref = getItemDetailHref(timelineCurrentItem);
    if (!itemHref) {
      return baseCardElement;
    }

    return (
      <Link key={itemKey} to={itemHref} className={`block no-underline flex-1${isGrouped && isCurrentItemLinked ? ' min-w-[512px]' : ''}`}>
        {baseCardElement}
      </Link>
    );
  };

  const renderReplyContents = (reply: TimelineItem): React.ReactNode => {
    const timelineReply = reply as TimelineItem;

    if ((timelineReply as any).type === 'note') {
      return hasText(timelineReply.description) ? <MarkdownContent content={timelineReply.description} /> : null;
    }

    const replyDescription = timelineReply.description;
    const descriptionNode = hasText(replyDescription) ? <MarkdownContent content={replyDescription} /> : null;
    const replyCardConfig = createTimelineCard(timelineReply, {
      size: 'x-large',
      alertId: entityId,
      entityType,
      linkTemplates,
    });

    let children: React.ReactNode = descriptionNode;

    if (isAlertItem(timelineReply)) {
      replyCardConfig.size = 'x-large';
      clearCardLines(replyCardConfig);

      const replyAlertData: Partial<AlertRead> & { title: string } = {
        id: timelineReply.alert_id || 0,
        human_id: timelineReply.alert_id ? convertNumericToAlertId(timelineReply.alert_id) : undefined,
        title:
          timelineReply.title ||
          (timelineReply.alert_id ? convertNumericToAlertId(timelineReply.alert_id) : 'Alert'),
        description: timelineReply.description,
        priority: timelineReply.priority,
        status: ((timelineReply as TimelineItem & { status?: AlertStatus | null }).status ?? 'NEW') as AlertStatus,
        created_at: timelineReply.created_at || '',
        updated_at:
          (timelineReply as TimelineItem & { updated_at?: string }).updated_at ||
          timelineReply.created_at ||
          '',
        assignee: timelineReply.assignee,
        tags: timelineReply.tags,
        source: (timelineReply as TimelineItem & { source?: string }).source,
        case_id: (timelineReply as TimelineItem & { case_id?: number }).case_id,
      };

      children = (
        <div className="w-full pt-2 flex flex-col gap-3">
          {descriptionNode}
          <AlertCard alertId={timelineReply.alert_id || 0} data={replyAlertData} />
        </div>
      );
    }

    const baseCardElement = <BaseCard {...replyCardConfig}>{children}</BaseCard>;
    const replyHref = getItemDetailHref(timelineReply);

    return (
      <div className="flex w-full flex-col items-start gap-3">
        {replyHref ? (
          <Link to={replyHref} className="block w-full no-underline">
            {baseCardElement}
          </Link>
        ) : (
          baseCardElement
        )}
      </div>
    );
  };

  // Build contents for the activity item
  // All items render description as markdown, with cards shown below for non-note types
  let contents: React.ReactNode = null;

  if (isNoteItem(item) && !isGrouped) {
    // Single note displays as plain markdown content without card framing
    contents = (
      <div className="flex w-full flex-col items-start gap-3">
        {item.description && (
          <MarkdownContent content={item.description} />
        )}
      </div>
    );
  } else {
    // For grouped items or non-note items:
    // 1. Render description as markdown (if present) ONLY for notes
    // 2. Render cards below the description (descriptions embedded in cards for non-notes)
    const itemDescription = item.description;
    const hasDescription = hasText(itemDescription);
    const isNote = isNoteItem(item);
    
    contents = (
      <div className="flex w-full flex-col items-start gap-3">
        {/* Render description as markdown for grouped notes */}
        {isNote && hasDescription && (
          <MarkdownContent content={itemDescription} />
        )}
        
        {/* Render cards below description for non-note items */}
        <div className="flex w-full flex-wrap items-start gap-3">
          {itemsToRender.map((currentItem, cardIndex) => renderTopLevelCard(currentItem, cardIndex))}
        </div>
      </div>
    );
  }

  // Render nested replies - flatten multi-level nesting into single-level thread
  const itemReplies = item.replies as TimelineItem[] | null | undefined;
  const hasReplies = itemReplies && Array.isArray(itemReplies) && itemReplies.length > 0;
  
  // For alert/task items, also include source_timeline_items (timeline from the linked entity)
  const sourceTimelineItems = (item as any).source_timeline_items as TimelineItem[] | null | undefined;
  const hasSourceItems = sourceTimelineItems && Array.isArray(sourceTimelineItems) && sourceTimelineItems.length > 0;
  
  // Track IDs of source timeline items (these should be read-only since they belong to the linked entity)
  const sourceItemIds = new Set<string>();
  if (hasSourceItems) {
    collectItemIds(sourceTimelineItems, sourceItemIds);
  }
  
  // Count source items for the toggle button label
  const sourceItemCount = hasSourceItems ? flattenReplies(sourceTimelineItems).length : 0;
  
  // Combine replies: only include source items when expanded, always include user replies
  const combinedReplies: TimelineItem[] = [];
  if (hasSourceItems && sourceItemsExpanded) {
    combinedReplies.push(...sourceTimelineItems);
  }
  if (hasReplies) {
    combinedReplies.push(...flattenReplies(itemReplies));
  }
  
  // Flatten all nested replies into a single array
  const flattenedReplies = combinedReplies.length > 0 ? flattenReplies(combinedReplies) : [];
  
  // Determine if we should show the toggle (for alert/task/case items with source timeline items)
  const showSourceToggle = hasSourceItems && (isAlertItem(item) || isTaskItem(item) || isCaseItem(item));

  // Build replies node if there are any (or if we have a toggle to show)
  const replies = (flattenedReplies.length > 0 || showSourceToggle) ? (
    <>
      {/* Toggle button for source timeline items - styled like ActivityItem hover bar */}
      {showSourceToggle && (
        <div 
          className="flex h-16 w-full items-center gap-1"
          onMouseEnter={() => setIsSourceToggleHovered(true)}
          onMouseLeave={() => setIsSourceToggleHovered(false)}
        >
          <div className={`flex w-full items-center gap-1 ${isSourceToggleHovered || sourceItemsExpanded ? '' : 'hidden'}`}>
            <Button
              size="small"
              variant="neutral-tertiary"
              icon={sourceItemsExpanded ? <ChevronDown /> : <ChevronRight />}
              onClick={() => setSourceItemsExpanded(!sourceItemsExpanded)}
            >
              {sourceItemsExpanded
                ? `Hide ${getSourceEntityLabel(item)} timeline (${sourceItemCount})`
                : `Show ${getSourceEntityLabel(item)} timeline (${sourceItemCount})`}
            </Button>
            <div className="flex h-px grow shrink-0 basis-0 flex-col items-center gap-2 bg-neutral-border" />
          </div>
        </div>
      )}
      {flattenedReplies.map((reply: TimelineItem, replyIndex: number) => {
        const ReplyIcon = getTimelineItemIcon(reply.type || 'note');
        const replyAction = `${getTimelineItemAction(reply.type || 'note')} ${getTimelineItemLabel(reply.type || 'note')}`;
        
        const replyUsername = reply.created_by || 'System';
        const isLastReply = replyIndex === flattenedReplies.length - 1;

        const replyContents = renderReplyContents(reply);

        // Check if this reply is from source_timeline_items (read-only)
        // Also check if this reply is a linked item type (alert, case, task)
        const isSourceItem = reply.id ? sourceItemIds.has(reply.id) : false;
        const isReplyLinkedType = reply.type === 'alert' || reply.type === 'case' || reply.type === 'task';
        const isReplyReadOnly = isSourceItem || isReplyLinkedType;

        return (
          <ActivityItem
            key={reply.id || `reply-${replyIndex}`}
            id={`timeline-item-${reply.id}`}
            itemId={reply.id || ''}
            username={replyUsername}
            icon={<ReplyIcon />}
            flagged={reply.flagged}
            highlighted={reply.highlighted}
            action={replyAction}
            displayItemId={reply.id}
            timestampValue={reply.timestamp || null}
            createdAtValue={reply.created_at || null}
            sortBy={sortBy}
            readOnly={isReplyReadOnly}
            end={isLastReply}
            replyEnabled={isLastReply && !isReplyReadOnly} // Only allow reply on the last flattened reply (not source/injected items)
            contents={replyContents}
            onFlag={isReplyReadOnly ? undefined : onFlag}
            onHighlight={isReplyReadOnly ? undefined : onHighlight}
            onDelete={isReplyReadOnly ? undefined : onDelete}
            onEdit={isReplyReadOnly ? undefined : onEdit}
            onReply={onReply}
          />
        );
      })}
    </>
  ) : null;

  // Determine if this item has any visible "children" (replies, toggle, or expanded source items)
  const hasVisibleChildren = flattenedReplies.length > 0 || showSourceToggle;

  return (
    <ActivityItem
      key={item.id}
      id={`timeline-item-${item.id}`}
      itemId={item.id || ''}
      username={username}
      icon={<Icon />}
      flagged={item.flagged}
      highlighted={item.highlighted}
      action={action}
      displayItemId={item.id}
      timestampValue={item.timestamp || null}
      createdAtValue={item.created_at || null}
      sortBy={sortBy}
      replyEnabled={!hasVisibleChildren} // Only show reply button if no replies/source items exist
      readOnly={readOnly}
      variant={variant}
      end={index === total - 1 && !hasVisibleChildren} // Don't end if there are children
      contents={contents}
      replies={replies}
      onFlag={onFlag}
      onHighlight={onHighlight}
      onDelete={onDelete}
      onEdit={onEdit}
      onReply={onReply}
      // Group-level actions (Option 1)
      isGrouped={isGrouped}
      groupItemIds={groupItemIds}
      onDeleteBatch={onDeleteBatch}
    />
  );
}

export default TimelineItemRenderer;
