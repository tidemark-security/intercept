"use client";

import React, { useState, useEffect, useMemo, useCallback } from "react";
import { useParams } from 'react-router-dom';
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { ThreeColumnLayout } from "@/components/layout/ThreeColumnLayout";
import { getPersistedCollapsedState, getPersistedWidth, persistCollapsedState } from "@/components/layout/ColumnRail";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { RightDock } from '@/components/layout/RightDock';
import { useCaseDetail } from "@/hooks/useCaseDetail";
import { convertHumanIdToNumeric } from "@/utils/caseHelpers";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateCase } from "@/hooks/useUpdateCase";
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
import { getTimelineItems } from "@/utils/timelineHelpers";
import type { TimelineItemType } from '@/types/drafts';
import type { AlertStatus } from '@/types/generated/models/AlertStatus';
import type { CaseStatus } from '@/types/generated/models/CaseStatus';
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { NotFoundError } from "@/pages/NotFoundError";
import { AiChat } from "@/components/ai";

/**
 * Case Detail Page - View and edit a specific case
 * 
 * Features:
 * - AI Chat placeholder on left (with hide/show on desktop/tablet)
 * - Editable timeline in center with full controls
 * - RightDock for editing timeline items
 * - Full timeline editing with all 17 timeline item types
 * - Mobile-friendly with single-column navigation
 * 
 * @returns The Case Detail page component
 */
function CaseDetailPage() {
  const { humanId } = useParams<{ humanId: string }>();
  const navigate = useViewTransitionNavigate();
  const { user, isAuditor } = useSession();
  const currentUser = user?.username || null;

  // Convert humanId to numeric ID synchronously to avoid timing issues
  const selectedCaseId = useMemo(() => {
    if (!humanId) return null;
    return convertHumanIdToNumeric(humanId);
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

  // Right Dock state for three-column layout (with automatic persistence per case)
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
  } = useDockState(selectedCaseId);

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

  // Fetch selected case details from API
  // Include linked timelines to embed alert/task timeline items as nested source_timeline_items
  const {
    data: caseDetail,
    isLoading: isLoadingDetail,
    error: detailError,
  } = useCaseDetail(selectedCaseId, { includeLinkedTimelines: true });

  // Check if the error is a 404
  const is404Error = detailError && (
    (detailError as any)?.status === 404 ||
    (detailError as any)?.response?.status === 404 ||
    detailError.message?.includes('404') ||
    detailError.message?.includes('not found')
  );

  // Case update mutation
  const updateCaseMutation = useUpdateCase(selectedCaseId, {
    onError: (error) => {
      console.error("Failed to update case:", error);
    },
  });

  // Timeline item mutations
  const updateTimelineItemMutation = useUpdateTimelineItem(selectedCaseId, 'case', {
    onError: (error) => {
      console.error("Failed to update timeline item:", error);
    },
  });

  const deleteTimelineItemMutation = useDeleteTimelineItem(selectedCaseId, 'case', {
    onError: (error) => {
      console.error("Failed to delete timeline item:", error);
    },
  });

  // Quick terminal mutation for rapid note creation
  const quickTerminalMutation = useQuickTerminalSubmit({
    entityId: selectedCaseId,
    entityType: "case"
  });



  // Auto-scroll to newly created timeline item
  useAutoScroll({
    elementId: scrollToItemId,
    idPrefix: 'timeline-item-',
    enabled: !!caseDetail,
    onScrollComplete: () => setScrollToItemId(null),
    onScrollFailed: () => setScrollToItemId(null),
  });

  // Assignment handlers (unified hook)
  const {
    handleAssignToMe,
    handleAssignToUser,
    handleUnassign,
  } = useAssignmentHandlers({
    entityType: 'case',
    entityId: selectedCaseId,
  });

  // Status handlers (unified hook)
  const {
    handleCloseEntity: handleCloseCase,
    handleReopenEntity: handleReopenCase,
  } = useStatusHandlers({
    entityType: 'case',
    entityId: selectedCaseId,
  });

  const getEditStatusPatch = useCallback((): { status?: CaseStatus } => {
    if (caseDetail?.status === 'NEW') {
      return { status: 'IN_PROGRESS' };
    }
    return {};
  }, [caseDetail?.status]);

  const handleUpdateTags = (tags: string[]) => {
    if (!selectedCaseId) return;
    updateCaseMutation.mutate({
      tags,
      ...getEditStatusPatch(),
    });
  };

  const handleEditCase = () => {
    if (!caseDetail) return;
    openDockForEdit('case_edit', caseDetail);
    switchToColumnOnMobile('right');
  };

  const handleCloseCaseWithDetails = useCallback((payload: {
    alert_closure_updates: Array<{ alert_id: number; status: AlertStatus }>;
    tags: string[];
  }) => {
    if (!selectedCaseId) return;

    updateCaseMutation.mutate({
      status: 'CLOSED',
      alert_closure_updates: payload.alert_closure_updates,
      tags: payload.tags,
    });
  }, [selectedCaseId, updateCaseMutation]);

  // Timeline item handler functions
  const handleFlagItem = (itemId: string) => {
    if (!selectedCaseId || !caseDetail) return;

    const timelineItems = getTimelineItems(caseDetail);
    const currentItem = timelineItems ? findTimelineItem(timelineItems, itemId) : null;
    const currentFlagged = currentItem?.flagged || false;

    updateTimelineItemMutation.mutate({
      itemId,
      updates: { flagged: !currentFlagged },
    });

    if (caseDetail.status === 'NEW') {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    }
  };

  const handleHighlightItem = (itemId: string) => {
    if (!selectedCaseId || !caseDetail) return;

    const timelineItems = getTimelineItems(caseDetail);
    const currentItem = timelineItems ? findTimelineItem(timelineItems, itemId) : null;
    const currentHighlighted = currentItem?.highlighted || false;

    updateTimelineItemMutation.mutate({
      itemId,
      updates: { highlighted: !currentHighlighted },
    });

    if (caseDetail.status === 'NEW') {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    }
  };

  const handleEditItem = (itemId: string) => {
    if (!selectedCaseId || !caseDetail) return;

    const timelineItems = getTimelineItems(caseDetail);
    const itemToEdit = timelineItems ? findTimelineItem(timelineItems, itemId) : null;

    if (itemToEdit && itemToEdit.type) {
      const dockType = mapItemTypeToDockType(itemToEdit.type);
      openDockForEdit(dockType, itemToEdit);
      switchToColumnOnMobile('right');
    }
  };

  const handleDeleteItem = (itemId: string) => {
    if (caseDetail?.status === 'NEW') {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    }

    deleteTimelineItemMutation.mutate({
      itemId,
    });
  };

  const handleDeleteBatch = (itemIds: string[]) => {
    if (caseDetail?.status === 'NEW' && itemIds.length > 0) {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    }

    itemIds.forEach((itemId) => {
      deleteTimelineItemMutation.mutate({
        itemId,
      });
    });
  };

  // Quick Terminal handlers
  const handleQuickTerminalSubmit = async (noteText: string, parentItemId?: string): Promise<void> => {
    if (caseDetail?.status === 'NEW') {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    }

    const result = await quickTerminalMutation.mutateAsync({ noteText, parentItemId });
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
    if (caseDetail?.status === 'NEW') {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    }

    if (itemId) {
      setScrollToItemId(itemId);
    }
    closeDock();
    switchToColumnOnMobile('center');
  };

  const handleAssignToMeWithStatusUpdate = useCallback(() => {
    if (!selectedCaseId || !currentUser) return;

    if (caseDetail?.status === 'NEW') {
      updateCaseMutation.mutate({ assignee: currentUser, status: 'IN_PROGRESS' });
      return;
    }

    handleAssignToMe();
  }, [selectedCaseId, currentUser, caseDetail?.status, updateCaseMutation, handleAssignToMe]);

  const handleAssignToUserWithStatusUpdate = useCallback((username: string) => {
    if (!selectedCaseId) return;

    if (caseDetail?.status === 'NEW') {
      updateCaseMutation.mutate({ assignee: username, status: 'IN_PROGRESS' });
      return;
    }

    handleAssignToUser(username);
  }, [selectedCaseId, caseDetail?.status, updateCaseMutation, handleAssignToUser]);

  const handleUnassignWithStatusUpdate = useCallback(() => {
    if (!selectedCaseId) return;

    if (caseDetail?.status === 'NEW') {
      updateCaseMutation.mutate({ assignee: null, status: 'IN_PROGRESS' });
      return;
    }

    handleUnassign();
  }, [selectedCaseId, caseDetail?.status, updateCaseMutation, handleUnassign]);

  const handleBackToList = () => {
    navigate('/cases');
  };

  // Custom column config for Case Detail page - standardized left column width
  const caseDetailColumnConfig = {
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

  // Show 404 error if case not found
  if (is404Error) {
    return (
      <DefaultPageLayout>
        <NotFoundError
          entityType="case"
          entityId={humanId}
          onBackToList={handleBackToList}
        />
      </DefaultPageLayout>
    );
  }

  return (
    <DefaultPageLayout priority={caseDetail?.priority || undefined}>
      <ThreeColumnLayout
        leftColumn={
          <AiChat
            contextType="case"
            entityId={selectedCaseId ?? undefined}
            entityHumanId={caseDetail?.human_id}
            username={currentUser ?? undefined}
            onClose={handleToggleAiPane}
          />
        }
        centerColumn={
          <div className="relative flex h-full w-full">
            <UnifiedTimeline
              entityDetail={caseDetail ?? null}
              entityType="case"
              selectedEntityId={selectedCaseId}
              currentUser={currentUser}
              isLoading={isLoadingDetail}
              error={detailError}
              users={users}
              usersLoading={isLoadingUsers}
              isUpdating={updateCaseMutation.isPending}
              isOverlayOpen={dockOpen}
              mode={isAuditor ? 'readonly' : 'editable'}
              onFlagItem={handleFlagItem}
              onHighlightItem={handleHighlightItem}
              onEditItem={handleEditItem}
              onDeleteItem={handleDeleteItem}
              onDeleteBatch={handleDeleteBatch}
              onAssignToMe={isAuditor ? undefined : handleAssignToMeWithStatusUpdate}
              onAssignToUser={isAuditor ? undefined : handleAssignToUserWithStatusUpdate}
              onUnassign={isAuditor ? undefined : handleUnassignWithStatusUpdate}
              onCloseEntity={isAuditor ? undefined : handleCloseCase}
              onCloseCaseWithDetails={isAuditor ? undefined : handleCloseCaseWithDetails}
              onReopenEntity={isAuditor ? undefined : handleReopenCase}
              onUpdateTags={isAuditor ? undefined : handleUpdateTags}
              onEditEntity={isAuditor ? undefined : handleEditCase}
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
          selectedCaseId !== null ? (
            <RightDock
              caseId={selectedCaseId}
              isOpen={dockOpen}
              itemType={dockItemType}
              onClose={handleDockClose}
              onItemCreated={handleItemCreated}
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
        columnConfig={caseDetailColumnConfig}
        showLeftRail={breakpoint !== 'mobile'}
        leftRailCollapsed={aiPaneCollapsed}
        onLeftRailToggle={handleToggleAiPane}
        leftColumnWidth={aiPaneWidth}
        onLeftColumnWidthChange={setAiPaneWidth}
      />
    </DefaultPageLayout>
  );
}

export default CaseDetailPage;
