import React, { useState, useMemo, useRef } from 'react';
import { EntityHeader, type SortOption, type SortDirection, type TimelineViewMode } from '@/components/entities/EntityHeader';
import { QuickTerminal } from '@/components/forms/QuickTerminal';
import { TimelineItemRenderer } from '@/components/timeline/TimelineItemRenderer';
import { TimelineGraphView } from '@/components/timeline/TimelineGraphView';
import { InlineReplyTerminal } from '@/components/timeline/InlineReplyTerminal';
import { ReplyProvider } from '@/contexts/ReplyProvider';
import { useReplyMode } from '@/contexts/ReplyContext';
import { usePresence } from '@/contexts/WebSocketContext';
import { useAutoScrollToTimelineItem, groupTimelineItems } from '@/components/timeline/timelineUtils';
import { useLinkTemplates } from '@/hooks/useLinkTemplates';
import { TriageRecommendationCard } from '@/components/triage/TriageRecommendationCard';
import { TriageRequestCard } from '@/components/triage/TriageRequestCard';
// Import handlers to ensure they're registered
import '@/components/timeline/eventHandlers';
import type { UnifiedTimelineProps, UnifiedEntity } from './UnifiedTimeline.types';
import type { TimelineItem } from '@/types/timeline';
import type { TimelineItemType } from '@/types/drafts';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import InterceptLogo from '@/assets/Intercept-Green.svg';
import InterceptLogoBlack from '@/assets/Intercept-Black.svg';
import { EntityMetadataCard } from '@/components/cards/EntityMetadataCard';
import { Button } from '@/components/buttons/Button';
import { Dialog } from "@/components/overlays/Dialog";
import { findTimelineItem } from "@/utils/timelineUtils";
import { compareTimelineItems, getTimelineItems } from "@/utils/timelineHelpers";
import { useTheme } from '@/contexts/ThemeContext';
import { cn } from '@/utils/cn';
import { formatPresenceText } from '@/utils/presenceText';


import { ArrowRight } from 'lucide-react';

const TIMELINE_VIEW_STORAGE_KEY = 'intercept.timeline-view';

function getTimelineViewStorageKey(entityType: 'case' | 'task', entityId: number): string {
  return `${TIMELINE_VIEW_STORAGE_KEY}.${entityType}.${entityId}`;
}
/**
 * UnifiedTimeline - Displays entity details, timeline items, and quick terminal
 * 
 * Features:
 * - Entity header with assignment controls
 * - Entity details summary card (separate from timeline)
 * - Timeline with recursive rendering of items and replies
 * - Support for various item types (system, actor, note, etc.)
 * - Quick terminal for rapid note creation
 * - Mobile back button for navigation
 * - Auto-scroll to new items
 * - Read-only preview mode support
 * 
 * @example
 * ```tsx
 * <UnifiedTimeline
 *   entityDetail={alertDetail}
 *   entityType="alert"
 *   selectedEntityId={selectedAlertId}
 *   currentUser={currentUser}
 *   isLoading={isLoadingDetail}
 *   error={detailError}
 *   users={users}
 *   usersLoading={isLoadingUsers}
 *   isUpdating={updateAlertMutation.isPending}
 *   onFlagItem={handleFlagItem}
 *   // ... other handlers
 * />
 * ```
 */
export function UnifiedTimeline(props: UnifiedTimelineProps) {
  const { resolvedTheme } = useTheme();
  const logoSrc = resolvedTheme === 'dark' ? InterceptLogo : InterceptLogoBlack;

  // Don't render if no entity is selected
  if (props.selectedEntityId === null) {
    return (
      <div className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-2 self-stretch rounded-md px-12 py-12">
        <img
          className="flex-none"
          src={logoSrc}
          alt="Intercept Logo"
        />
      </div>
    );
  }

  return (
    <ReplyProvider
      entityId={props.selectedEntityId}
      entityType={props.entityType}
    >
      <UnifiedTimelineInner {...props} selectedEntityId={props.selectedEntityId} />
    </ReplyProvider>
  );
}

function UnifiedTimelineInner({
  entityDetail,
  entityType,
  selectedEntityId,
  currentUser,
  isLoading,
  error,
  users,
  usersLoading,
  isUpdating,
  presenceText,
  isOverlayOpen = false,
  mode = 'editable',
  onFlagItem,
  onHighlightItem,
  onEditItem,
  onDeleteItem,
  onDeleteBatch,
  onAssignToMe,
  onAssignToUser,
  onUnassign,
  onCloseEntity,
  onCloseCaseWithDetails,
  onReopenEntity,
  onUpdateTags,
  onOpenEntity,
  onLinkToCase,
  onUnlinkFromCase,
  onEditEntity,
  onQuickTerminalSubmit,
  onSlashCommand,
  onAddNote,
  onMenuItemSelect,
  onPasteFiles,
  isSubmittingNote,
  showAiChatButton,
  onAiChatClick,
  onBackToList,
  scrollToItemId,
  onReplyParentIdChange,
  onAcceptTriageRecommendation,
  onRejectTriageRecommendation,
  onScrollToTimelineItem,
  onNavigateToCase,
  isAcceptingRecommendation,
  isRejectingRecommendation,
  onRetryTriage,
  onRequestTriage,
  isEnqueuingTriage,
  isTriageEnabled,
}: UnifiedTimelineProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === 'dark';
  const presenceViewers = usePresence(entityType, selectedEntityId);
  const resolvedPresenceText = useMemo(
    () => presenceText ?? formatPresenceText(presenceViewers, entityType, currentUser),
    [currentUser, entityType, presenceText, presenceViewers],
  );
  const logoSrc = isDarkTheme ? InterceptLogo : InterceptLogoBlack;

  // Access reply context
  const { activeReplyParentId, activeReplyDepth, enterReplyMode, exitReplyMode, isInReplyMode } = useReplyMode();
  
  // Ref for the scrollable timeline items container (for scroll-based hide/show on mobile)
  const timelineScrollRef = useRef<HTMLDivElement>(null);
  
  const isReadOnly = mode === 'readonly';
  const isEditable = mode === 'editable';
  const canReviewTriage = isEditable && !!onAcceptTriageRecommendation && !!onRejectTriageRecommendation;
  const canRequestTriage = isEditable && !!onRequestTriage;

  // Notify parent component when reply parent ID changes
  React.useEffect(() => {
    onReplyParentIdChange?.(activeReplyParentId);
  }, [activeReplyParentId, onReplyParentIdChange]);
  
  // Handle Escape key to exit reply mode
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isInReplyMode()) {
        exitReplyMode();
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isInReplyMode, exitReplyMode]);
  
  // Fetch link templates for timeline items
  const { data: linkTemplates = [] } = useLinkTemplates(true);

  // Auto-scroll to newly created timeline item by ID
  useAutoScrollToTimelineItem(scrollToItemId, entityDetail, isEditable);

  const linkedCaseAlerts = useMemo(() => {
    if (entityType !== 'case') {
      return [];
    }

    const alerts = (entityDetail as any)?.alerts as Array<AlertRead> | undefined;
    if (!alerts || !Array.isArray(alerts)) {
      return [];
    }

    return alerts.map((alert) => ({
      id: alert.id,
      human_id: alert.human_id,
      title: alert.title,
      status: alert.status as AlertStatus,
    }));
  }, [entityDetail, entityType]);

  const linkedTaskCount = useMemo(() => {
    if (entityType !== 'case') {
      return 0;
    }

    const timelineItems = getTimelineItems(entityDetail);
    const taskIdSet = new Set<number>();
    timelineItems.forEach((item) => {
      if (item.type === 'task' && typeof (item as any).task_id === 'number') {
        taskIdSet.add((item as any).task_id);
      }
    });
    return taskIdSet.size;
  }, [entityDetail, entityType]);

  const caseTags = useMemo(() => {
    if (entityType !== 'case') {
      return [];
    }
    return entityDetail?.tags || [];
  }, [entityDetail?.tags, entityType]);

  const supportsGraphView = entityType === 'case' || entityType === 'task';

  // Timeline filter and sort state - defaults: Timestamp / Ascending / All / Grouped
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  const [sortBy, setSortBy] = useState<SortOption>('timestamp');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [groupSimilar, setGroupSimilar] = useState<boolean>(true);
  const [timelineViewMode, setTimelineViewMode] = useState<TimelineViewMode>('timeline');

  const updateTimelineViewMode = React.useCallback((nextMode: TimelineViewMode) => {
    setTimelineViewMode(nextMode);

    if (!supportsGraphView || selectedEntityId === null || typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(
      getTimelineViewStorageKey(entityType, selectedEntityId),
      nextMode,
    );
  }, [entityType, selectedEntityId, supportsGraphView]);

  React.useEffect(() => {
    if (!supportsGraphView || selectedEntityId === null || typeof window === 'undefined') {
      setTimelineViewMode('timeline');
      return;
    }

    const persistedMode = window.localStorage.getItem(
      getTimelineViewStorageKey(entityType, selectedEntityId),
    );

    setTimelineViewMode(persistedMode === 'graph' ? 'graph' : 'timeline');
  }, [entityType, selectedEntityId, supportsGraphView]);

  const handleSortChange = (newSortBy: SortOption, newDirection: SortDirection) => {
    setSortBy(newSortBy);
    setSortDirection(newDirection);
  };

  const handleGraphSelectItem = React.useCallback((itemId: string) => {
    onScrollToTimelineItem?.(itemId);
    updateTimelineViewMode('timeline');

    window.setTimeout(() => {
      document.getElementById(`timeline-item-${itemId}`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }, 0);
  }, [onScrollToTimelineItem, updateTimelineViewMode]);

  const sortedTimelineItems = useMemo(() => {
    const timelineItems = getTimelineItems(entityDetail);
    if (timelineItems.length === 0) {
      return [];
    }

    const sorted = timelineItems
      .map((item, index) => ({ item, index }))
      .sort((a, b) => compareTimelineItems(a.item, b.item, sortBy, sortDirection) || a.index - b.index)
      .map(({ item }) => item);

    return sorted;
  }, [entityDetail, sortBy, sortDirection]);

  // Filter and sort timeline items
  const filteredAndSortedItems = useMemo(() => {
    if (!selectedType) {
      return sortedTimelineItems;
    }

    return sortedTimelineItems.filter((item) => item.type === selectedType);
  }, [selectedType, sortedTimelineItems]);

  // Helper function to calculate reply depth for a timeline item
  const calculateReplyDepth = (item: TimelineItem, items: TimelineItem[]): number => {
    let depth = 0;
    let currentParentId = item.parent_id;
    
    // Walk up the parent chain (max 6 iterations for safety)
    while (currentParentId && depth < 6) {
      const parent = items.find((i) => i.id === currentParentId);
      if (!parent) break;
      depth++;
      currentParentId = parent.parent_id;
    }
    
    return depth;
  };


  // Reply handler
  const handleReply = React.useCallback((itemId: string) => {
    if (isReadOnly) return;

    const allItems = getTimelineItems(entityDetail);
    if (allItems.length === 0) return;

    const findItemById = (targetId: string, items: TimelineItem[]): TimelineItem | null => {
      for (const item of items) {
        if (item.id === targetId) return item;

        const itemReplies = getTimelineItems({ timeline_items: item.replies ?? null });
        if (itemReplies.length > 0) {
          const found = findItemById(targetId, itemReplies);
          if (found) return found;
        }
      }
      return null;
    };

    const findRootParent = (item: TimelineItem, items: TimelineItem[]): TimelineItem => {
      if (!item.parent_id) return item;

      let current = item;
      let iterations = 0;
      while (current.parent_id && iterations < 6) {
        const parent = findItemById(current.parent_id, items);
        if (!parent) break;
        current = parent;
        iterations++;
      }

      return current;
    };
    
    // Recursively search for the item (could be nested reply)
    const item = findItemById(itemId, allItems);
    if (!item) return;
    
    // For Slack-style threading: always reply to the root parent, not the nested item
    const rootParent = findRootParent(item, allItems);
    const depth = calculateReplyDepth(item, allItems);
    
    // Enter reply mode with the ROOT parent ID (so all replies are siblings under the same parent)
    enterReplyMode(rootParent.id || itemId, depth);
  }, [entityDetail, enterReplyMode, isReadOnly]);
  
  // Reply submission handler (wraps existing onQuickTerminalSubmit)
  const handleReplySubmit = React.useCallback(async (text: string) => {
    if (!onQuickTerminalSubmit) return;

    if (!activeReplyParentId) {
      // Not in reply mode, use normal handler
      await onQuickTerminalSubmit(text);
      return;
    }
    
    // In reply mode - submit as reply with parent_id
    await onQuickTerminalSubmit(text, activeReplyParentId);
    
    // Keep reply mode active for additional replies
    // User can press Escape or click Cancel to exit
  }, [activeReplyParentId, onQuickTerminalSubmit]);

  // Wrap slash command handler to include parent_id context
  const handleSlashCommand = React.useCallback((itemType: TimelineItemType) => {
    // Store the current parent_id in the callback so RightDock can access it
    // This is necessary because onSlashCommand opens RightDock in the parent page
    // which doesn't have direct access to reply context
    onSlashCommand?.(itemType);
  }, [onSlashCommand]);

  // Wrap add note handler to include parent_id context
  const handleAddNote = React.useCallback(() => {
    onAddNote?.();
  }, [onAddNote]);

  // Wrap menu item select handler to include parent_id context
  const handleMenuItemSelect = React.useCallback((itemType: TimelineItemType) => {
    onMenuItemSelect?.(itemType);
  }, [onMenuItemSelect]);

  // Delete confirmation state
  const [deleteConfirmItemIds, setDeleteConfirmItemIds] = useState<string[]>([]);
  const suppressGlobalSlashFocus = isOverlayOpen || deleteConfirmItemIds.length > 0;

  const handleInternalDelete = (itemId: string) => {
    setDeleteConfirmItemIds([itemId]);
  };

  const handleInternalBatchDelete = (itemIds: string[]) => {
    setDeleteConfirmItemIds(itemIds);
  };

  const handleCancelDelete = () => {
    setDeleteConfirmItemIds([]);
  };

  const handleConfirmDelete = () => {
    if (deleteConfirmItemIds.length === 0) return;
    
    if (deleteConfirmItemIds.length === 1 && onDeleteItem) {
      onDeleteItem(deleteConfirmItemIds[0]);
    } else if (onDeleteBatch) {
      onDeleteBatch(deleteConfirmItemIds);
    } else if (onDeleteItem) {
      // Fallback if no batch handler but multiple items
      deleteConfirmItemIds.forEach(id => onDeleteItem(id));
    }
    
    setDeleteConfirmItemIds([]);
  };

  // Calculate total children count for items being deleted
  const deleteChildCount = useMemo(() => {
    if (!entityDetail || deleteConfirmItemIds.length === 0) return 0;
    
    const timelineItems = getTimelineItems(entityDetail);
    if (!timelineItems) return 0;
    
    const countDescendants = (item: TimelineItem): number => {
      let c = 0;
      const replies = getTimelineItems({ timeline_items: item.replies ?? null });
      for (const reply of replies) {
        c += 1 + countDescendants(reply);
      }
      return c;
    };
    
    let count = 0;
    for (const id of deleteConfirmItemIds) {
      const item = findTimelineItem(timelineItems, id);
      if (item) {
        count += countDescendants(item);
      }
    }
    
    return count;
  }, [entityDetail, deleteConfirmItemIds]);

  // Check if entity is closed (API returns UPPERCASE status values)
  const isEntityClosed = entityDetail?.status && (
    entityDetail.status === 'CLOSED' ||
    [
      'CLOSED_TP',
      'CLOSED_BP',
      'CLOSED_FP',
      'CLOSED_UNRESOLVED',
      'CLOSED_DUPLICATE',
    ].includes(entityDetail.status)
  );

  // If no entity selected, show placeholder
  if (!selectedEntityId) {
    return (
      <div className="flex grow shrink-0 basis-0 flex-col items-center justify-center gap-2 self-stretch rounded-md px-12 py-12">
        <img
          className="flex-none"
          src={logoSrc}
          alt="Intercept Logo"
        />
      </div>
    );
  }

  // Determine available item types based on entity type
  // Alerts: no task items allowed (they are created via case)
  // Cases: all item types including task items
  // Tasks: all item types EXCEPT task (tasks cannot be nested)
  const availableItemTypes: TimelineItemType[] = entityType === 'alert' 
    ? [
        'note',
        'attachment',
        'link',
        'observable',
        'system',
        'actor',
        'email',
        'network_traffic',
        'process',
        'registry_change',
        'ttp',
      ]
    : entityType === 'task'
    ? [
        'note',
        'attachment',
        'link',
        'observable',
        'system',
        'actor',
        'email',
        'network_traffic',
        'process',
        'registry_change',
        'ttp',
        'forensic_artifact',
      ]
    : [
        'note',
        'attachment',
        'link',
        'task',
        'observable',
        'system',
        'actor',
        'email',
        'network_traffic',
        'process',
        'registry_change',
        'ttp',
        'forensic_artifact',
      ];

  return (
    <div className="flex h-full w-full flex-col items-start">
      {/* Entity Header */}
      <div className={`flex min-h-[150px] mobile:min-h-0 w-full flex-col items-start p-6 mobile:p-4 border-b border-solid  ${isDarkTheme ? 'border-brand-primary' : 'border-neutral-1000'}`}>
        <EntityHeader
          entityType={entityType}
          mode={mode}
          createdDate={entityDetail?.created_at ? `Created: ${new Date(entityDetail.created_at).toLocaleString()}` : ''}
          updatedDate={entityDetail?.updated_at ? `Updated: ${new Date(entityDetail.updated_at).toLocaleString()}` : ''}
          id={entityDetail?.human_id || ''}
          description={entityDetail?.title || `Select a ${entityType}`}
          status={entityDetail?.status}
          assignee={entityDetail?.assignee || null}
          priority={entityDetail?.priority || null}
          caseId={entityType === 'alert' || entityType === 'task' ? (entityDetail as any)?.case_id : null}
          currentUser={currentUser}
          users={users}
          isLoadingUsers={usersLoading}
          isUpdating={isUpdating}
          presenceText={resolvedPresenceText}
          onAssignToMe={onAssignToMe}
          onAssignToUser={onAssignToUser}
          onUnassign={onUnassign}
          onCloseAlert={onCloseEntity}
          onCloseCaseWithDetails={onCloseCaseWithDetails}
          onReopenAlert={onReopenEntity}
          onLinkToCase={onLinkToCase}
          onUnlinkFromCase={onUnlinkFromCase}
          onPrimaryAction={onOpenEntity}
          onEdit={onEditEntity}
          showTimelineViewToggle={supportsGraphView}
          timelineViewMode={timelineViewMode}
          onTimelineViewModeChange={updateTimelineViewMode}
          graphViewDisabled={getTimelineItems(entityDetail).length === 0}
          linkedCaseAlerts={linkedCaseAlerts}
          linkedTaskCount={linkedTaskCount}
          caseTags={caseTags}
          showTimelineFilter={true}
          timelineItems={getTimelineItems(entityDetail)}
          selectedType={selectedType}
          onTypeChange={setSelectedType}
          sortBy={sortBy}
          sortDirection={sortDirection}
          onSortChange={handleSortChange}
          groupSimilar={groupSimilar}
          onGroupSimilarChange={setGroupSimilar}
          showBackButton={!!onBackToList}
          onBackClick={onBackToList}
          scrollContainerRef={timelineScrollRef}
        />
      </div>

      
      {/* Timeline Items */}
      <div
        ref={timelineScrollRef}
        className={cn(
          'flex w-full grow shrink-0 basis-0 flex-col items-start',
          timelineViewMode === 'graph'
            ? 'min-h-0 overflow-hidden p-0'
            : 'overflow-auto p-0'
        )}
      >
        {isLoading ? (
          <div className="flex w-full h-full items-center justify-center">
            <span className="text-body font-body text-subtext-color">Loading {entityType} details...</span>
          </div>
        ) : error ? (
          <div className="flex w-full h-full items-center justify-center">
            <span className="text-body font-body text-error-color">Error loading {entityType} details</span>
          </div>
        ) : entityDetail ? (
          supportsGraphView && timelineViewMode === 'graph' ? (
            <TimelineGraphView
              items={sortedTimelineItems}
              selectedType={selectedType}
              entityId={selectedEntityId}
              entityType={entityType as 'case' | 'task'}
              sortBy={sortBy}
              linkTemplates={linkTemplates}
              onSelectItem={handleGraphSelectItem}
              onFlagItem={isEditable ? onFlagItem : undefined}
              onHighlightItem={isEditable ? onHighlightItem : undefined}
              onEditItem={isEditable ? onEditItem : undefined}
              onDeleteItem={isEditable ? handleInternalDelete : undefined}
            />
          ) : (
            <>
              {(() => {
              const timelineItems = getTimelineItems(entityDetail);
              const hasTimelineItems = timelineItems.length > 0;
              
              return (
                <div className="flex w-full flex-col items-start">
                  {/* Triage Recommendation Card (Alerts only) */}
                  {entityType === 'alert' && (entityDetail as AlertRead).triage_recommendation && (
                    <div className="flex w-full px-6 pt-6 mobile:px-2 mobile:pt-2">
                      <TriageRecommendationCard
                        recommendation={(entityDetail as AlertRead).triage_recommendation!}
                        onAccept={onAcceptTriageRecommendation || (() => {})}
                        onReject={onRejectTriageRecommendation || (() => {})}
                        onRetry={canReviewTriage ? onRetryTriage : undefined}
                        onNavigateToCase={onNavigateToCase}
                        isAccepting={isAcceptingRecommendation}
                        isRejecting={isRejectingRecommendation}
                        isRetrying={isEnqueuingTriage}
                        canReview={canReviewTriage}
                      />
                    </div>
                  )}
                  
                  {/* Triage Request Card (Alerts only - when no recommendation exists and triage is enabled) */}
                  {entityType === 'alert' && 
                   !(entityDetail as AlertRead).triage_recommendation && 
                   isTriageEnabled && 
                   canRequestTriage && (
                    <div className="flex w-full px-6 pt-6 mobile:px-2 mobile:pt-2">
                      <TriageRequestCard
                        onRequestTriage={onRequestTriage}
                        isEnqueuing={isEnqueuingTriage}
                      />
                    </div>
                  )}
                  
                  {/* Entity Metadata Card */}
                  <div className="flex w-full">
                    <EntityMetadataCard
                      entity={entityDetail}
                      entityType={entityType}
                      isLoading={isLoading}
                      onUpdateTags={onUpdateTags}
                    />
                  </div>

                  {/* Timeline Items */}
                  <div className="flex w-full flex-col items-start p-6 mobile:p-2">
                    {hasTimelineItems && filteredAndSortedItems.length > 0 ? (
                    (() => {
                      // Conditionally group timeline items based on groupSimilar toggle
                      if (groupSimilar) {
                        const groupedItems = groupTimelineItems(filteredAndSortedItems);
                        
                        return groupedItems.map((group) => (
                          <TimelineItemRenderer
                            key={group.item.id}
                            item={group.item}
                            items={group.items}
                            index={group.index}
                            total={filteredAndSortedItems.length}
                            entityId={selectedEntityId}
                            entityType={entityType}
                            sortBy={sortBy}
                            onFlag={isEditable ? onFlagItem : undefined}
                            onHighlight={isEditable ? onHighlightItem : undefined}
                            onEdit={isEditable ? onEditItem : undefined}
                            onDelete={isEditable ? handleInternalDelete : undefined}
                            onDeleteBatch={isEditable ? handleInternalBatchDelete : undefined}
                            onReply={isEditable ? handleReply : undefined}
                            linkTemplates={linkTemplates}
                          />
                        ));
                      } else {
                        // Render items without grouping
                        return filteredAndSortedItems.map((item, index) => (
                          <TimelineItemRenderer
                            key={item.id}
                            item={item}
                            index={index}
                            total={filteredAndSortedItems.length}
                            entityId={selectedEntityId}
                            entityType={entityType}
                            sortBy={sortBy}
                            onFlag={isEditable ? onFlagItem : undefined}
                            onHighlight={isEditable ? onHighlightItem : undefined}
                            onEdit={isEditable ? onEditItem : undefined}
                            onDelete={isEditable ? handleInternalDelete : undefined}
                            onReply={isEditable ? handleReply : undefined}
                            linkTemplates={linkTemplates}
                          />
                        ));
                      }
                    })()
                  ) : hasTimelineItems && filteredAndSortedItems.length === 0 ? (
                    <div className="flex w-full h-full items-center justify-center pt-4">
                      <span className="text-body font-body text-subtext-color">
                        No timeline items match the selected filter
                      </span>
                    </div>
                  ) : (
                    <div className="flex w-full h-full items-center justify-center pt-4">
                      <span className="text-body font-body text-subtext-color">
                        No timeline items yet
                      </span>
                    </div>
                  )}
                  </div>
                </div>
              );
            })()}
            </>
          )
        ) : (
          <div className="flex w-full h-full items-center justify-center">
            <span className="text-body font-body text-subtext-color">No {entityType} data available</span>
          </div>
        )}
      </div>

      {/* Open Entity Button for Read-Only Mode (Case/Task Preview) */}
      {isReadOnly && (entityType === 'case' || entityType === 'task') && onOpenEntity && (
        <div className="flex w-full items-start gap-4 p-6 mobile:p-2 border-t border-solid border-neutral-border">
          <Button
            className="w-full"
            variant="brand-primary"
            size="large"
            onClick={onOpenEntity}
            iconRight={<ArrowRight />}
          >
            {entityType === 'task' ? 'Open Task' : 'Open Case'}
          </Button>
        </div>
      )}

      {/* Quick Terminal for rapid note-taking (hide when in reply mode) */}
      {isEditable && !isInReplyMode() && onQuickTerminalSubmit && onSlashCommand && onAddNote && onMenuItemSelect && (
        <div className="flex w-full items-start gap-4 p-6 mobile:p-2 border-t border-solid border-neutral-border">
          <QuickTerminal
            entityId={selectedEntityId}
            entityType={entityType}
            availableItemTypes={availableItemTypes}
            onSlashCommand={onSlashCommand}
            onSubmitNote={onQuickTerminalSubmit}
            onAddNote={onAddNote}
            onMenuItemSelect={onMenuItemSelect}
            disabled={isEntityClosed}
            isSubmitting={isSubmittingNote}
            showAiChatButton={showAiChatButton}
            onAiChatClick={onAiChatClick}
            enableGlobalSlashFocus={true}
            suppressGlobalSlashFocus={suppressGlobalSlashFocus}
            onPasteFiles={onPasteFiles}
          />
        </div>
      )}
      
      {/* Inline Reply Terminal (show when in reply mode) */}
      {isEditable && isInReplyMode() && activeReplyParentId && onQuickTerminalSubmit && onSlashCommand && onAddNote && onMenuItemSelect && (
        <div className="flex w-full items-start gap-4 p-6 mobile:p-2 border-t border-solid border-neutral-border">
          <InlineReplyTerminal
            entityId={selectedEntityId}
            entityType={entityType}
            parentItemId={activeReplyParentId}
            parentItemType="item"
            replyDepth={activeReplyDepth}
            onSlashCommand={onSlashCommand}
            onSubmitNote={handleReplySubmit}
            onAddNote={onAddNote}
            onMenuItemSelect={onMenuItemSelect}
            onCancel={exitReplyMode}
            disabled={isEntityClosed}
            isSubmitting={isSubmittingNote}
            enableGlobalSlashFocus={true}
            suppressGlobalSlashFocus={suppressGlobalSlashFocus}
          />
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmItemIds.length > 0} onOpenChange={(open) => !open && handleCancelDelete()}>
        <Dialog.Content>
          <div className="flex w-full flex-col items-start gap-4 p-6">
            <div className="flex w-full flex-col items-start gap-2">
              <span className="text-heading-3 font-heading-3 text-default-font">
                Delete {deleteConfirmItemIds.length} Timeline Item{deleteConfirmItemIds.length !== 1 ? 's' : ''}
                {deleteChildCount > 0 && ` and ${deleteChildCount} Child${deleteChildCount !== 1 ? 'ren' : ''}`}
              </span>
              <span className="text-body font-body text-subtext-color">
                Are you sure you want to delete {deleteConfirmItemIds.length === 1 ? 'this timeline item' : `these ${deleteConfirmItemIds.length} items`}
                {deleteChildCount > 0 && ` and ${deleteChildCount === 1 ? 'its' : 'their'} ${deleteChildCount} descendant${deleteChildCount !== 1 ? 's' : ''}`}? 
                This action cannot be undone.
              </span>
            </div>
            <div className="flex w-full items-center justify-end gap-2">
              <Button
                variant="neutral-secondary"
                size="medium"
                onClick={handleCancelDelete}
              >
                Cancel
              </Button>
              <Button
                variant="destructive-primary"
                size="medium"
                onClick={handleConfirmDelete}
              >
                Delete
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog>
    </div>
  );
}

export default UnifiedTimeline;
