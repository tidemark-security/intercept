"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useParams } from 'react-router-dom';
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { convertTaskHumanIdToNumeric } from '@/utils/humanIdHelpers';
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { ThreeColumnLayout } from "@/components/layout/ThreeColumnLayout";
import { getPersistedCollapsedState, getPersistedWidth, persistCollapsedState } from "@/components/layout/ColumnRail";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { RightDock } from '@/components/layout/RightDock';
import { useTaskDetail } from "@/hooks/useTaskDetail";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateTask } from "@/hooks/useUpdateTask";
import { useUpdateTimelineItem } from "@/hooks/useUpdateTimelineItem";
import { useDeleteTimelineItem } from "@/hooks/useDeleteTimelineItem";
import { useQuickTerminalSubmit } from "@/hooks/useQuickTerminalSubmit";
import { useSession } from "@/contexts/sessionContext";
import { useBreakpointContext } from "@/contexts/BreakpointContext";
import { useDockState } from "@/hooks/useDockState";
import { useColumnNavigation } from "@/hooks/useColumnNavigation";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { useAssignmentHandlers } from "@/hooks/useAssignmentHandlers";
import { useStatusHandlers } from "@/hooks/useStatusHandlers";
import { findTimelineItem, mapItemTypeToDockType } from "@/utils/timelineUtils";
import { getTimelineItems, getTimelineItemProperty } from "@/utils/timelineHelpers";
import type { TimelineItemType } from '@/types/drafts';
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { NotFoundError } from "@/pages/NotFoundError";
import { AiChat } from "@/components/ai";

/**
 * Task Detail Page - View and edit a specific task
 * 
 * Features:
 * - AI Chat placeholder on left (with hide/show on desktop/tablet)
 * - Editable timeline in center with full controls
 * - RightDock for editing timeline items
 * - Full timeline editing with all timeline item types
 * - Mobile-friendly with single-column navigation
 * 
 * @returns The Task Detail page component
 */
function TaskDetailPage() {
  const { humanId } = useParams<{ humanId: string }>();
  const navigate = useViewTransitionNavigate();
  const { user, isAuditor } = useSession();
  const currentUser = user?.username || null;

  // Convert humanId to numeric ID synchronously to avoid timing issues
  const selectedTaskId = useMemo(() => {
    if (!humanId) return null;
    return convertTaskHumanIdToNumeric(humanId);
  }, [humanId]);

  // Reactive breakpoint state from app-level context (prevents layout flash)
  const { breakpoint, getInitialVisibleColumns } = useBreakpointContext();

  // Column visibility state - initialize from breakpoint context to prevent flash
  const [visibleColumns, setVisibleColumns] = useState<VisibleColumns>(() => getInitialVisibleColumns(false));

  // Column navigation helpers (must be after setVisibleColumns is defined)
  const { switchToColumnOnMobile } = useColumnNavigation(setVisibleColumns);

  // AI pane visibility and resizable width (persisted in localStorage)
  // Persist the assistant visibility globally across case/task detail pages.
  const [aiPaneCollapsed, setAiPaneCollapsed] = useState(() => {
    const defaultCollapsed = typeof window !== 'undefined' && window.innerWidth < 768;
    return getPersistedCollapsedState(defaultCollapsed);
  });
  const [aiPaneWidth, setAiPaneWidth] = useState<number>(() =>
    getPersistedWidth(breakpoint === 'ultrawide' ? 512 : 320)
  );

  // Toggle AI pane visibility
  const handleToggleAiPane = useCallback(() => {
    setAiPaneCollapsed(prev => {
      const next = !prev;
      persistCollapsedState(next);
      return next;
    });
  }, []);

  // Right Dock state for three-column layout (with automatic persistence per task)
  const {
    isOpen: dockOpen,
    itemType: dockItemType,
    editMode: dockEditMode,
    itemData: dockItemData,
    pendingFiles,
    openDock,
    openDockForEdit,
    openDockWithFiles,
    clearPendingFiles,
    closeDock,
  } = useDockState(selectedTaskId);

  // Track newly created item for auto-scrolling
  const [scrollToItemId, setScrollToItemId] = useState<string | null>(null);
  
  // Track active reply parent ID from UnifiedTimeline for RightDock
  const [replyParentId, setReplyParentId] = useState<string | null>(null);

  // Automatically adjust visible columns based on screen size, dock state, and AI pane state
  useEffect(() => {
    if (breakpoint === 'mobile') {
      // Mobile: show single column at a time based on AI pane state
      // When AI chat is open (not collapsed) → show AI chat (left)
      // When AI chat is closed (collapsed) → show timeline (center)
      setVisibleColumns(aiPaneCollapsed ? 'center' : 'left');
    } else if (breakpoint === 'ultrawide') {
      // Ultrawide: always show AI chat unless collapsed
      if (aiPaneCollapsed) {
        setVisibleColumns(dockOpen ? 'center+right' : 'center');
      } else {
        setVisibleColumns(dockOpen ? 'all' : 'left+center');
      }
    } else if (breakpoint === 'desktop' || breakpoint === 'tablet') {
      // Desktop/Tablet: respect aiPaneCollapsed toggle
      if (aiPaneCollapsed) {
        setVisibleColumns(dockOpen ? 'center+right' : 'center');
      } else {
        setVisibleColumns(dockOpen ? 'all' : 'left+center');
      }
    }
  }, [dockOpen, breakpoint, aiPaneCollapsed]);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch selected task details from API
  // Include linked timelines to embed case/alert timeline items as nested source_timeline_items
  const {
    data: taskDetail,
    isLoading: isLoadingDetail,
    error: detailError,
  } = useTaskDetail(selectedTaskId, { includeLinkedTimelines: true });

  // Check if the error is a 404
  const is404Error = detailError && (
    (detailError as any)?.status === 404 ||
    (detailError as any)?.response?.status === 404 ||
    detailError.message?.includes('404') ||
    detailError.message?.includes('not found')
  );

  // Task update mutation
  const updateTaskMutation = useUpdateTask(selectedTaskId, {
    onError: (error) => {
      console.error("Failed to update task:", error);
    },
  });

  // Timeline item mutations
  const updateTimelineItemMutation = useUpdateTimelineItem(selectedTaskId, 'task', {
    onError: (error) => {
      console.error("Failed to update timeline item:", error);
    },
  });

  const deleteTimelineItemMutation = useDeleteTimelineItem(selectedTaskId, 'task', {
    onError: (error) => {
      console.error("Failed to delete timeline item:", error);
    },
  });

  // Quick terminal mutation for rapid note creation
  const quickTerminalMutation = useQuickTerminalSubmit({
    entityId: selectedTaskId,
    entityType: "task"
  });

  // Auto-scroll to newly created timeline item
  useAutoScroll({
    elementId: scrollToItemId,
    idPrefix: 'timeline-item-',
    enabled: !!taskDetail,
    onScrollComplete: () => setScrollToItemId(null),
    onScrollFailed: () => setScrollToItemId(null),
  });

  // Assignment handlers (unified hook)
  const {
    handleAssignToMe,
    handleAssignToUser,
    handleUnassign,
    checkAndAssignToMe,
  } = useAssignmentHandlers({
    entityType: 'task',
    entityId: selectedTaskId,
    currentStatus: taskDetail?.status,
    currentAssignee: taskDetail?.assignee,
  });

  // Status handlers (unified hook)
  const {
    handleCloseEntity: handleCloseTask,
    handleReopenEntity: handleReopenTask,
  } = useStatusHandlers({
    entityType: 'task',
    entityId: selectedTaskId,
  });

  const handleUpdateTags = (tags: string[]) => {
    if (!selectedTaskId) return;
    updateTaskMutation.mutate({ tags });
  };

  const handleEditTask = () => {
    if (!taskDetail) return;
    openDockForEdit('task_edit', taskDetail);
    switchToColumnOnMobile('right');
  };

  // Timeline item handler functions
  const handleFlagItem = (itemId: string) => {
    if (!selectedTaskId || !taskDetail) return;

    const currentFlagged = getTimelineItemProperty(taskDetail, itemId, 'flagged');
    updateTimelineItemMutation.mutate({
      itemId,
      updates: { flagged: !currentFlagged },
    });
  };

  const handleHighlightItem = (itemId: string) => {
    if (!selectedTaskId || !taskDetail) return;

    const currentHighlighted = getTimelineItemProperty(taskDetail, itemId, 'highlighted');
    updateTimelineItemMutation.mutate({
      itemId,
      updates: { highlighted: !currentHighlighted },
    });
  };

  const handleEditItem = (itemId: string) => {
    if (!selectedTaskId || !taskDetail) return;

    const timelineItems = getTimelineItems(taskDetail);
    const itemToEdit = timelineItems ? findTimelineItem(timelineItems, itemId) : null;

    if (itemToEdit && itemToEdit.type) {
      const dockType = mapItemTypeToDockType(itemToEdit.type);
      openDockForEdit(dockType, itemToEdit);
      switchToColumnOnMobile('right');
    }
  };

  const handleDeleteItem = (itemId: string) => {
    deleteTimelineItemMutation.mutate({
      itemId,
    });
  };

  const handleDeleteBatch = (itemIds: string[]) => {
    itemIds.forEach((itemId) => {
      deleteTimelineItemMutation.mutate({
        itemId,
      });
    });
  };

  // Quick Terminal handlers
  const handleQuickTerminalSubmit = async (noteText: string, parentItemId?: string): Promise<void> => {
    const result = await quickTerminalMutation.mutateAsync({ noteText, parentItemId });
    
    // Auto-assign if needed
    checkAndAssignToMe();

    if (result?.itemId) {
      handleItemCreated(result.itemId);
    }
  };

  const handleSlashCommand = (itemType: TimelineItemType) => {
    openDock(itemType);
    switchToColumnOnMobile('right');
  };

  const handleAddNote = () => {
    openDock("note");
    switchToColumnOnMobile('right');
  };

  const handleMenuItemSelect = (itemType: TimelineItemType) => {
    openDock(itemType);
    switchToColumnOnMobile('right');
  };

  const handlePasteFiles = (files: File[]) => {
    openDockWithFiles(files);
    switchToColumnOnMobile('right');
  };

  const handleDockClose = () => {
    closeDock();
    switchToColumnOnMobile('center');
  };

  const handleItemCreated = (itemId?: string) => {
    if (itemId) {
      setScrollToItemId(itemId);
    }
    closeDock();
    switchToColumnOnMobile('center');
  };

  // Wrapper for dock item creation to handle auto-assignment
  const handleDockItemCreated = (itemId?: string) => {
    // Only auto-assign if we are creating a new item (not editing)
    if (!dockEditMode) {
      checkAndAssignToMe();
    }
    handleItemCreated(itemId);
  };

  const handleBackToList = () => {
    navigate('/tasks');
  };

  // Custom column config for Task Detail page - narrower left column for AI chat
  const taskDetailColumnConfig = {
    ultrawide: {
      leftWidth: 'w-[512px] shrink-0',
      centerWidth: 'flex-1',
      rightWidth: 'w-[512px] shrink-0',
    },
    desktop: {
      leftWidth: 'w-[512px] shrink-0',
      centerWidth: 'flex-1',
      rightWidth: 'w-[512px] shrink-0',
    },
    tablet: {
      leftWidth: 'w-[512px] shrink-0',
      centerWidth: 'flex-1',
      rightWidth: 'w-[512px] shrink-0',
    },
    mobile: {
      leftWidth: 'w-full',
      centerWidth: 'w-full',
      rightWidth: 'w-full',
    },
  };

  // Show 404 error if task not found
  if (is404Error) {
    return (
      <DefaultPageLayout>
        <NotFoundError
          entityType="task"
          entityId={humanId}
          onBackToList={handleBackToList}
        />
      </DefaultPageLayout>
    );
  }

  return (
    <DefaultPageLayout priority={taskDetail?.priority || undefined}>
      <ThreeColumnLayout
        leftColumn={
          <AiChat
            contextType="task"
            entityId={selectedTaskId ?? undefined}
            entityHumanId={taskDetail?.human_id}
            username={currentUser ?? undefined}
            onClose={handleToggleAiPane}
          />
        }
        centerColumn={
          <div className="relative flex h-full w-full">
            <UnifiedTimeline
              entityDetail={taskDetail ?? null}
              entityType="task"
              selectedEntityId={selectedTaskId}
              currentUser={currentUser}
              isLoading={isLoadingDetail}
              error={detailError}
              users={users}
              usersLoading={isLoadingUsers}
              isUpdating={updateTaskMutation.isPending}
              isOverlayOpen={dockOpen}
              mode={isAuditor ? 'readonly' : 'editable'}
              onFlagItem={handleFlagItem}
              onHighlightItem={handleHighlightItem}
              onEditItem={handleEditItem}
              onDeleteItem={handleDeleteItem}
              onDeleteBatch={handleDeleteBatch}
              onAssignToMe={isAuditor ? undefined : handleAssignToMe}
              onAssignToUser={isAuditor ? undefined : handleAssignToUser}
              onUnassign={isAuditor ? undefined : handleUnassign}
              onCloseEntity={isAuditor ? undefined : handleCloseTask}
              onReopenEntity={isAuditor ? undefined : handleReopenTask}
              onUpdateTags={isAuditor ? undefined : handleUpdateTags}
              onEditEntity={isAuditor ? undefined : handleEditTask}
              onQuickTerminalSubmit={handleQuickTerminalSubmit}
              onSlashCommand={handleSlashCommand}
              onAddNote={handleAddNote}
              onMenuItemSelect={handleMenuItemSelect}
              onPasteFiles={handlePasteFiles}
              isSubmittingNote={quickTerminalMutation.isPending}
              showAiChatButton={aiPaneCollapsed}
              onAiChatClick={handleToggleAiPane}
              onBackToList={handleBackToList}
              scrollToItemId={scrollToItemId}
              onReplyParentIdChange={setReplyParentId}
            />
          </div>
        }
        rightColumn={
          selectedTaskId !== null ? (
            <RightDock
              taskId={selectedTaskId}
              isOpen={dockOpen}
              itemType={dockItemType}
              onClose={handleDockClose}
              onItemCreated={handleDockItemCreated}
              editMode={dockEditMode}
              itemData={dockItemData}
              parentItemId={replyParentId}
              pendingFiles={pendingFiles}
              onPendingFilesConsumed={clearPendingFiles}
            />
          ) : (
            <div />
          )
        }
        visibleColumns={visibleColumns}
        onVisibleColumnsChange={setVisibleColumns}
        columnConfig={taskDetailColumnConfig}
        showLeftRail={breakpoint !== 'mobile'}
        leftRailCollapsed={aiPaneCollapsed}
        onLeftRailToggle={handleToggleAiPane}
        leftColumnWidth={aiPaneWidth}
        onLeftColumnWidthChange={setAiPaneWidth}
      />
    </DefaultPageLayout>
  );
}

export default TaskDetailPage;
