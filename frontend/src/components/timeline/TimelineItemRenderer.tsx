import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '@/contexts/ThemeContext';
import { ActivityItem } from '@/components/data-display/ActivityItem';
import { BaseCard } from '@/components/cards/BaseCard';
import { Badge } from '@/components/data-display/Badge';
import { AlertCard } from '@/components/timeline/AlertCard';
import { AlertCardContent } from '@/components/timeline/AlertCardContent';
import { TaskCardContent } from '@/components/timeline/TaskCardContent';
import { CaseCardContent } from '@/components/timeline/CaseCardContent';
import { TimelineDescriptionBlock } from '@/components/timeline/TimelineDescriptionBlock';
import { GoogleWorkspaceEnrichmentBlock } from '@/components/timeline/GoogleWorkspaceEnrichmentBlock';
import { MaxMindEnrichmentBlock } from '@/components/timeline/MaxMindEnrichmentBlock';
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
import { compareTimelineItems, getTimelineItems } from '@/utils/timelineHelpers';
import { isAlertItem, isDeletedItem, isNoteItem, isTaskItem } from '@/types/timeline';
import type { CaseItem } from '@/types/generated/models/CaseItem';
import { convertNumericToAlertId, convertNumericToHumanId } from '@/utils/caseHelpers';
import { useEnqueueItemEnrichment } from '@/hooks/useEnqueueItemEnrichment';
import { cn } from '@/utils/cn';

import { Button } from '@/components/buttons/Button';
import { IconButton } from '@/components/buttons/IconButton';

import { ArrowRight, ChevronDown, ChevronRight, MessageSquareReply as ReplyIcon, RefreshCw } from 'lucide-react';
import { Tooltip } from '@/components/overlays/Tooltip';
import {
  isTimelineItemEnrichmentActive,
  isTimelineItemEnrichable,
  isTimelineItemEnrichmentFailed,
} from './timelineUtils';
/**
 * Type guard for CaseItem
 */
function isCaseItem(item: TimelineItem): item is TimelineItem & CaseItem {
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

function getTimelineTags(item: TimelineItem): string[] {
  const tags = (item as TimelineItem & { tags?: string[] | null }).tags;

  return Array.isArray(tags) ? tags : [];
}

function withEnrichmentBlocks(
  item: TimelineItem,
  bodyChildren: React.ReactNode,
  footerChildren?: React.ReactNode
): React.ReactNode {
  return (
    <div className="flex w-full flex-1 flex-col gap-3">
      {bodyChildren}
      <GoogleWorkspaceEnrichmentBlock item={item} />
      <MaxMindEnrichmentBlock item={item} />
      {footerChildren}
    </div>
  );
}

function isLinkedTimelineType(type: TimelineItem['type'] | undefined): boolean {
  return type === 'alert' || type === 'case' || type === 'task';
}

function sortRepliesForDisplay(items: TimelineItem[]): TimelineItem[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => compareTimelineItems(left.item, right.item) || left.index - right.index)
    .map(({ item }) => item);
}

function getDeletedItemTimestamp(item: TimelineItem): string | null {
  if (!isDeletedItem(item)) {
    return null;
  }

  return item.original_timestamp || item.original_created_at || item.deleted_at || null;
}

function flattenReplies(items: TimelineItem[]): TimelineItem[] {
  const flattened: TimelineItem[] = [];

  const traverse = (currentItems: TimelineItem[]) => {
    for (const currentItem of sortRepliesForDisplay(currentItems)) {
      flattened.push(currentItem);
      const nestedReplies = getTimelineItems({ timeline_items: currentItem.replies ?? null });
      if (nestedReplies.length > 0) {
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

    const nestedReplies = getTimelineItems({ timeline_items: currentItem.replies ?? null });
    if (nestedReplies.length > 0) {
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

function getSourceEntityDisplayLabel(item: TimelineItem): 'Alert' | 'Task' | 'Case' {
  if (isAlertItem(item)) {
    return 'Alert';
  }
  if (isTaskItem(item)) {
    return 'Task';
  }
  return 'Case';
}

function renderRefreshEnrichmentAction(
  timelineItem: TimelineItem,
  options: {
    enabled: boolean;
    isActive: boolean;
    isPending: boolean;
    pendingItemId?: string;
    onEnqueue: (itemId: string) => void;
  },
): React.ReactNode {
  if (!options.enabled || !timelineItem.id) {
    return null;
  }

  const isFailedEnrichment = isTimelineItemEnrichmentFailed(timelineItem);
  const isLoading = options.isActive || (options.isPending && options.pendingItemId === timelineItem.id);

  return (
    <div className="ml-auto flex items-center gap-2">
      {isFailedEnrichment ? <Badge variant="error">Enrichment Failed</Badge> : null}
      <Tooltip.Provider>
        <Tooltip.Root>
          <Tooltip.Trigger asChild>
            <IconButton
              
              size="small"
              onClick={(event) => {
                event.stopPropagation();
                options.onEnqueue(timelineItem.id!);
              }}
              loading={isLoading}
              disabled={isLoading}
              icon={<RefreshCw className="h-3.5 w-3.5" />}
              aria-label={isFailedEnrichment ? 'Retry enrichment' : 'Refresh enrichment'}
            />
          </Tooltip.Trigger>
          <Tooltip.Content side="bottom" align="center" sideOffset={8}>
            {isFailedEnrichment ? 'Retry enrichment' : 'Refresh enrichment'}
          </Tooltip.Content>
        </Tooltip.Root>
      </Tooltip.Provider>
    </div>
  );
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

  /** Hide timeline rail/icon chrome for compact embedded previews. */
  compactPreview?: boolean;
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
  compactPreview = false,
}: TimelineItemRendererProps) {
  const navigate = useNavigate();
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
  const variant = undefined;

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
  const enqueueItemEnrichment = useEnqueueItemEnrichment(
    entityType ?? 'alert',
    entityId,
  );

  const renderOpenEntityAction = (href: string, label: string): React.ReactNode => (
    <div className="ml-auto flex items-center gap-2">
      <Button
        variant="neutral-tertiary"
        size="small"
        onClick={(event) => {
          event.stopPropagation();
          navigate(href);
        }}
        iconRight={<ArrowRight className="h-3.5 w-3.5" />}
      >
        {label}
      </Button>
    </div>
  );

  const renderLinkedEntityFooter = (currentItem: TimelineItem, existingActionButtons?: React.ReactNode): React.ReactNode => {
    const currentDescription = currentItem.description;
    const hasDescriptionContent = hasText(currentDescription);
    const currentTags = getTimelineTags(currentItem);
    const href = getItemDetailHref(currentItem);
    const openAction = href ? renderOpenEntityAction(href, `Open ${getSourceEntityDisplayLabel(currentItem)}`) : null;
    const footerActions = existingActionButtons || openAction ? (
      <div className="flex w-full items-center gap-2">
        {existingActionButtons}
        {openAction}
      </div>
    ) : null;

    if (!hasDescriptionContent && !footerActions && currentTags.length === 0) {
      return null;
    }

    return (
      <TimelineDescriptionBlock actionButtons={footerActions} tags={currentTags} className="mt-auto">
        {hasDescriptionContent ? <MarkdownContent content={currentDescription} /> : null}
      </TimelineDescriptionBlock>
    );
  };
  
  // Collect all item IDs for group-level actions
  const groupItemIds = isGrouped ? itemsToRender.map(i => i.id || '').filter(Boolean) : [];

  if (isDeletedItem(item)) {
    const DeletedIcon = getTimelineItemIcon(item.original_type || 'note');
    // const deletedContents = (
    //   <div className="rounded-md border border-dashed border-neutral-border bg-neutral-50/40 px-3 py-3 text-body text-subtext-color">
    //     {`${item.original_type} deleted by ${item.deleted_by}`}
    //   </div>
    // );

    return (
      <ActivityItem
        key={item.id}
        id={`timeline-item-${item.id}`}
        itemId={item.id || ''}
        username={item.original_created_by || 'System'}
        icon={<DeletedIcon />}
        action={`deleted ${item.original_type}`}
        displayItemId={compactPreview ? undefined : item.id}
        timestampValue={getDeletedItemTimestamp(item)}
        createdAtValue={item.original_created_at || getDeletedItemTimestamp(item)}
        sortBy={sortBy}
        readOnly={true}
        hideRail={compactPreview}
        end={index === total - 1}
        contents={null}
      />
    );
  }

  const renderTopLevelCard = (currentItem: TimelineItem, cardIndex: number): React.ReactNode => {
    const timelineCurrentItem = currentItem as TimelineItem;
    const itemKey = timelineCurrentItem.id || `item-${cardIndex}`;

    if ((timelineCurrentItem as any).type === 'note') {
      return null;
    }

    const isEnrichable = !!entityType && entityId !== null && isTimelineItemEnrichable(timelineCurrentItem);
    const isEnrichmentActive = isTimelineItemEnrichmentActive(timelineCurrentItem);
    const refreshEnrichmentButton = renderRefreshEnrichmentAction(timelineCurrentItem, {
      enabled: isEnrichable,
      isActive: isEnrichmentActive,
      isPending: enqueueItemEnrichment.isPending,
      pendingItemId: enqueueItemEnrichment.variables?.itemId,
      onEnqueue: (itemId) => enqueueItemEnrichment.mutate({ itemId }),
    });

    const isCurrentItemLinked = isLinkedTimelineType(timelineCurrentItem.type);
    const cardConfig = createTimelineCard(timelineCurrentItem, {
      size: 'x-large',
      alertId: entityId,
      entityType,
      actionButtons: refreshEnrichmentButton,
      enableActionMenu: isGrouped,
      itemId: timelineCurrentItem.id,
      onFlag,
      onHighlight,
      onDelete,
      onEdit,
      readOnly: isCurrentItemLinked || !item.created_by,
      linkTemplates,
    });

    const { children: cardChildren, actionButtons: cardActionButtons, ...baseCardProps } = cardConfig;

    if (isAlertItem(timelineCurrentItem) || isTaskItem(timelineCurrentItem) || isCaseItem(timelineCurrentItem)) {
      baseCardProps.size = 'x-large';
    }

    baseCardProps.className = cn(
      baseCardProps.className,
      compactPreview && 'min-h-full max-w-none !border-0 !bg-transparent',
      isGrouped && `flex-1 self-stretch${isCurrentItemLinked ? ' min-w-40' : ''}`,
    );

    baseCardProps.enableCopyInteractions = !isAlertItem(timelineCurrentItem) && !isTaskItem(timelineCurrentItem) && !isCaseItem(timelineCurrentItem);

    const description = timelineCurrentItem.description;
    const shouldRenderInlineDescription = hasText(description) && timelineCurrentItem.type !== 'ttp';
    const currentTags = getTimelineTags(timelineCurrentItem);
    const shouldRenderTags = currentTags.length > 0;
    const shouldUseFooter = !isAlertItem(timelineCurrentItem) && !isTaskItem(timelineCurrentItem) && !isCaseItem(timelineCurrentItem) && (shouldRenderInlineDescription || shouldRenderTags || !!cardActionButtons);
    const descriptionNode = shouldUseFooter ? (
      <TimelineDescriptionBlock actionButtons={cardActionButtons} tags={currentTags} className="mt-auto">
        {shouldRenderInlineDescription ? <MarkdownContent content={description} /> : null}
      </TimelineDescriptionBlock>
    ) : null;
    let renderedActionButtons = descriptionNode ? undefined : cardActionButtons;

    const cardBody = cardChildren ? (
      <div className="flex w-full flex-1 flex-col gap-3">
        {cardChildren}
      </div>
    ) : null;

    let children: React.ReactNode = withEnrichmentBlocks(timelineCurrentItem, cardBody, descriptionNode);

    if (isAlertItem(timelineCurrentItem)) {
      baseCardProps.size = 'x-large';
      const alertId = timelineCurrentItem.alert_id ? convertNumericToAlertId(timelineCurrentItem.alert_id) : 'Alert';
      baseCardProps.title = buildEntityTitle(alertId, timelineCurrentItem.title, isDarkTheme);
      clearCardLines(baseCardProps);

      const alertData: Partial<AlertRead> & { title: string } = {
        id: timelineCurrentItem.alert_id || 0,
        human_id: timelineCurrentItem.alert_id ? convertNumericToAlertId(timelineCurrentItem.alert_id) : undefined,
        title:
          timelineCurrentItem.title ||
          (timelineCurrentItem.alert_id ? convertNumericToAlertId(timelineCurrentItem.alert_id) : 'Alert'),
        description: undefined,
        priority: timelineCurrentItem.priority,
        status: ((timelineCurrentItem as TimelineItem & { status?: AlertStatus | null }).status ?? 'NEW') as AlertStatus,
        created_at: timelineCurrentItem.created_at || '',
        updated_at:
          (timelineCurrentItem as TimelineItem & { updated_at?: string }).updated_at ||
          timelineCurrentItem.created_at ||
          '',
        assignee: timelineCurrentItem.assignee,
        source: (timelineCurrentItem as TimelineItem & { source?: string }).source,
        case_id: (timelineCurrentItem as TimelineItem & { case_id?: number }).case_id,
      };

      children = withEnrichmentBlocks(timelineCurrentItem, (
        <div className="w-full pt-2 flex flex-col gap-3">
          <AlertCardContent data={alertData} showTags={false} />
        </div>
      ), renderLinkedEntityFooter(timelineCurrentItem, cardActionButtons));
      renderedActionButtons = undefined;
    } else if (isTaskItem(timelineCurrentItem)) {
      baseCardProps.size = 'x-large';
      const taskId = timelineCurrentItem.task_human_id || 'Task';
      baseCardProps.title = buildEntityTitle(taskId, timelineCurrentItem.title, isDarkTheme);
      clearCardLines(baseCardProps, { clearCharacterFlags: true });

      const taskData: Partial<TaskRead> & { title: string } = {
        id: timelineCurrentItem.task_id || 0,
        human_id: timelineCurrentItem.task_human_id || '',
        title: timelineCurrentItem.title || (timelineCurrentItem.task_human_id || 'Task'),
        description: undefined,
        priority: timelineCurrentItem.priority ?? undefined,
        status: (timelineCurrentItem.status || 'OPEN') as TaskStatus,
        created_at: timelineCurrentItem.created_at || '',
        updated_at:
          (timelineCurrentItem as TimelineItem & { updated_at?: string }).updated_at ||
          timelineCurrentItem.created_at ||
          '',
        assignee: timelineCurrentItem.assignee,
        due_date: timelineCurrentItem.due_date,
        created_by: timelineCurrentItem.created_by || 'System',
        case_id: (timelineCurrentItem as TimelineItem & { case_id?: number }).case_id,
      };

      children = withEnrichmentBlocks(timelineCurrentItem, (
        <div className="w-full pt-2 flex flex-col gap-3">
          <TaskCardContent data={taskData} showTags={false} />
        </div>
      ), renderLinkedEntityFooter(timelineCurrentItem, cardActionButtons));
      renderedActionButtons = undefined;
    } else if (isCaseItem(timelineCurrentItem)) {
      baseCardProps.size = 'x-large';
      const caseHumanId = convertNumericToHumanId(timelineCurrentItem.case_id);
      baseCardProps.title = buildEntityTitle(caseHumanId, timelineCurrentItem.title, isDarkTheme);
      clearCardLines(baseCardProps);

      const caseData: Partial<CaseRead> & { title: string } = {
        id: timelineCurrentItem.case_id,
        human_id: caseHumanId,
        title: timelineCurrentItem.title || caseHumanId,
        description: undefined,
        priority: timelineCurrentItem.priority ?? undefined,
        status: ((timelineCurrentItem as TimelineItem & { status?: CaseStatus | null }).status ?? 'NEW') as CaseStatus,
        created_at: timelineCurrentItem.created_at || '',
        updated_at:
          (timelineCurrentItem as TimelineItem & { updated_at?: string }).updated_at ||
          timelineCurrentItem.created_at ||
          '',
        assignee: timelineCurrentItem.assignee,
        created_by: timelineCurrentItem.created_by || 'System',
      };

      children = withEnrichmentBlocks(timelineCurrentItem, (
        <div className="w-full pt-2 flex flex-col gap-3">
          <CaseCardContent data={caseData} showTags={false} />
        </div>
      ), renderLinkedEntityFooter(timelineCurrentItem, cardActionButtons));
      renderedActionButtons = undefined;
    }

    const baseCardElement = (
      <BaseCard key={itemKey} {...baseCardProps} actionButtons={renderedActionButtons}>
        {children}
      </BaseCard>
    );

    return baseCardElement;
  };

  const renderReplyContents = (reply: TimelineItem): React.ReactNode => {
    const timelineReply = reply as TimelineItem;

    if (isDeletedItem(timelineReply)) {
      return null;
    }

    if ((timelineReply as any).type === 'note') {
      return hasText(timelineReply.description) ? <MarkdownContent content={timelineReply.description} /> : null;
    }

    const replyDescription = timelineReply.description;
    const shouldRenderInlineDescription = hasText(replyDescription) && timelineReply.type !== 'ttp';
    const replyTags = getTimelineTags(timelineReply);
    const canRefreshEnrichment = !!entityType && entityId !== null && isTimelineItemEnrichable(timelineReply);
    const isReplyEnrichmentActive = isTimelineItemEnrichmentActive(timelineReply);
    const replyRefreshEnrichmentButton = renderRefreshEnrichmentAction(timelineReply, {
      enabled: canRefreshEnrichment,
      isActive: isReplyEnrichmentActive,
      isPending: enqueueItemEnrichment.isPending,
      pendingItemId: enqueueItemEnrichment.variables?.itemId,
      onEnqueue: (itemId) => enqueueItemEnrichment.mutate({ itemId }),
    });
    const replyCardConfig = createTimelineCard(timelineReply, {
      size: 'x-large',
      alertId: entityId,
      entityType,
      actionButtons: replyRefreshEnrichmentButton,
      linkTemplates,
    });

    const { children: replyCardChildren, actionButtons: replyCardActionButtons, ...baseReplyCardProps } = replyCardConfig;

    if (isAlertItem(timelineReply) || isTaskItem(timelineReply) || isCaseItem(timelineReply)) {
      baseReplyCardProps.size = 'x-large';
    }

    baseReplyCardProps.enableCopyInteractions = !isAlertItem(timelineReply) && !isTaskItem(timelineReply) && !isCaseItem(timelineReply);

    const shouldUseFooter = !isAlertItem(timelineReply) && !isTaskItem(timelineReply) && !isCaseItem(timelineReply) && (shouldRenderInlineDescription || replyTags.length > 0 || !!replyCardActionButtons);
    const descriptionNode = shouldUseFooter ? (
      <TimelineDescriptionBlock actionButtons={replyCardActionButtons} tags={replyTags} className="mt-auto">
        {shouldRenderInlineDescription ? <MarkdownContent content={replyDescription} /> : null}
      </TimelineDescriptionBlock>
    ) : null;
    let renderedReplyActionButtons = descriptionNode ? undefined : replyCardActionButtons;

    const replyCardBody = replyCardChildren ? (
      <div className="flex w-full flex-1 flex-col gap-3">
        {replyCardChildren}
      </div>
    ) : null;

    let children: React.ReactNode = withEnrichmentBlocks(timelineReply, replyCardBody, descriptionNode);

    if (isAlertItem(timelineReply)) {
      baseReplyCardProps.size = 'x-large';
      clearCardLines(baseReplyCardProps);

      const replyAlertData: Partial<AlertRead> & { title: string } = {
        id: timelineReply.alert_id || 0,
        human_id: timelineReply.alert_id ? convertNumericToAlertId(timelineReply.alert_id) : undefined,
        title:
          timelineReply.title ||
          (timelineReply.alert_id ? convertNumericToAlertId(timelineReply.alert_id) : 'Alert'),
        description: undefined,
        priority: timelineReply.priority,
        status: ((timelineReply as TimelineItem & { status?: AlertStatus | null }).status ?? 'NEW') as AlertStatus,
        created_at: timelineReply.created_at || '',
        updated_at:
          (timelineReply as TimelineItem & { updated_at?: string }).updated_at ||
          timelineReply.created_at ||
          '',
        assignee: timelineReply.assignee,
        source: (timelineReply as TimelineItem & { source?: string }).source,
        case_id: (timelineReply as TimelineItem & { case_id?: number }).case_id,
      };

      children = withEnrichmentBlocks(timelineReply, (
        <div className="w-full pt-2 flex flex-col gap-3">
          <AlertCard alertId={timelineReply.alert_id || 0} data={replyAlertData} showTags={false} />
        </div>
      ), renderLinkedEntityFooter(timelineReply, replyCardActionButtons));
      renderedReplyActionButtons = undefined;
    }

    const baseCardElement = <BaseCard {...baseReplyCardProps} actionButtons={renderedReplyActionButtons}>{children}</BaseCard>;

    return (
      <div className="flex w-full flex-col items-start gap-3">
        {baseCardElement}
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
      <div className={cn("flex w-full flex-col items-start gap-3", compactPreview && "min-h-full flex-1")}>
        {/* Render description as markdown for grouped notes */}
        {isNote && hasDescription && (
          <MarkdownContent content={itemDescription} />
        )}
        
        {/* Render cards below description for non-note items */}
        <div className={cn("flex w-full flex-wrap items-stretch gap-3", compactPreview && "min-h-full flex-1")}>
          {itemsToRender.map((currentItem, cardIndex) => renderTopLevelCard(currentItem, cardIndex))}
        </div>
      </div>
    );
  }

  // Render nested replies - flatten multi-level nesting into single-level thread
  const itemReplies = getTimelineItems({ timeline_items: item.replies ?? null });
  const hasReplies = itemReplies.length > 0;
  
  // For alert/task items, also include source_timeline_items (timeline from the linked entity)
  const sourceTimelineItems = getTimelineItems({ timeline_items: (item as any).source_timeline_items ?? null });
  const hasSourceItems = sourceTimelineItems.length > 0;
  
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
    combinedReplies.push(...itemReplies);
  }
  
  // Flatten all nested replies into a single array
  const flattenedReplies = combinedReplies.length > 0 ? flattenReplies(combinedReplies) : [];
  
  // Determine if we should show the toggle (for alert/task/case items with source timeline items)
  const showSourceToggle = !compactPreview && hasSourceItems && (isAlertItem(item) || isTaskItem(item) || isCaseItem(item));

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
        const isReplyDeleted = isDeletedItem(reply);
        const ReplyItemIcon = isReplyDeleted ? getTimelineItemIcon(reply.original_type || 'note') : ReplyIcon;
        const replyAction = isReplyDeleted
          ? `deleted ${reply.original_type}`
          : `${getTimelineItemAction(reply.type || 'note')} ${getTimelineItemLabel(reply.type || 'note')}`;
        
        const replyUsername = isReplyDeleted ? reply.original_created_by || 'System' : reply.created_by || 'System';
        const isLastReply = replyIndex === flattenedReplies.length - 1;

        const replyContents = renderReplyContents(reply);

        // Check if this reply is from source_timeline_items (read-only)
        // Also check if this reply is a linked item type (alert, case, task)
        const isSourceItem = reply.id ? sourceItemIds.has(reply.id) : false;
        const isReplyLinkedType = reply.type === 'alert' || reply.type === 'case' || reply.type === 'task';
        const isReplyReadOnly = isSourceItem || isReplyLinkedType || isReplyDeleted;
        const deletedReplyTargetId = isReplyDeleted && !isSourceItem ? reply.parent_id || null : null;
        const canReplyToDeletedReply = isLastReply && !!deletedReplyTargetId;
        const replyTimestampValue = isReplyDeleted ? getDeletedItemTimestamp(reply) : reply.timestamp || null;
        const replyCreatedAtValue = isReplyDeleted
          ? reply.original_created_at || getDeletedItemTimestamp(reply)
          : reply.created_at || null;

        return (
          <ActivityItem
            key={reply.id || `reply-${replyIndex}`}
            id={`timeline-item-${reply.id}`}
            itemId={reply.id || ''}
            username={replyUsername}
            icon={<ReplyItemIcon />}
            flagged={reply.flagged}
            highlighted={reply.highlighted}
            action={replyAction}
            displayItemId={compactPreview ? undefined : reply.id}
            timestampValue={replyTimestampValue}
            createdAtValue={replyCreatedAtValue}
            sortBy={sortBy}
            edited={reply.audit?.edited === true}
            readOnly={isReplyReadOnly}
            allowReplyWhenReadOnly={canReplyToDeletedReply}
            hideRail={compactPreview}
            end={isLastReply}
            replyEnabled={(isLastReply && !isReplyReadOnly) || canReplyToDeletedReply} // Deleted replies continue the parent thread.
            replyTargetId={deletedReplyTargetId || undefined}
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
      displayItemId={compactPreview ? undefined : item.id}
      timestampValue={item.timestamp || null}
      createdAtValue={item.created_at || null}
      sortBy={sortBy}
      edited={item.audit?.edited === true}
      replyEnabled={!hasVisibleChildren} // Only show reply button if no replies/source items exist
      readOnly={readOnly}
      hideRail={compactPreview}
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
