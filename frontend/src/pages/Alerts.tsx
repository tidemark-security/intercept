"use client";

import React, { useState, useEffect } from "react";
import { useLocation, useParams } from 'react-router-dom';
import { Copy, FolderPlus, Link2, X } from 'lucide-react';
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { Button } from "@/components/buttons/Button";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { Dialog } from "@/components/overlays/Dialog";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { EntityQueueLayout } from "@/components/layout/EntityQueueLayout";
import { getPersistedWidth } from "@/components/layout/ColumnRail";
import { EntityList } from "@/components/data-display/EntityList";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { RightDock } from '@/components/layout/RightDock';
import { BulkActionModal } from "@/components/entities/BulkActionModal";
import { CaseSelectorModal } from "@/components/entities/CaseSelectorModal";
import {
  DuplicateTargetSelectorModal,
  type DuplicateTargetSelection,
} from "@/components/entities/DuplicateTargetSelectorModal";
import { useAlerts } from "@/hooks/useAlerts";
import { useAlertDetail } from "@/hooks/useAlertDetail";
import { formatEntityTitle, useDocumentTitle } from "@/hooks/useDocumentTitle";
import { convertHumanIdToNumeric } from "@/hooks/useAlertIdFromHumanId";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateAlert } from "@/hooks/useUpdateAlert";
import { useTriageAlert } from "@/hooks/useTriageAlert";
import { useLinkAlertToCase } from "@/hooks/useLinkAlertToCase";
import { useUnlinkAlertFromCase } from "@/hooks/useUnlinkAlertFromCase";
import { useBulkAlertAction } from "@/hooks/useBulkAlertAction";
import { useEntityBulkActions } from "@/hooks/useEntityBulkActions";
import { useUpdateTimelineItem } from "@/hooks/useUpdateTimelineItem";
import { useDeleteTimelineItem } from "@/hooks/useDeleteTimelineItem";
import { useQuickTerminalSubmit } from "@/hooks/useQuickTerminalSubmit";
import { useAcceptTriageRecommendation } from "@/hooks/useAcceptTriageRecommendation";
import { useRejectTriageRecommendation } from "@/hooks/useRejectTriageRecommendation";
import { useEnqueueTriage } from "@/hooks/useEnqueueTriage";
import { useToast } from "@/contexts/ToastContext";
import { useFeatureFlags } from "@/hooks/useFeatureFlags";
import { useSession } from "@/contexts/sessionContext";
import { useURLFilters } from "@/hooks/useURLFilters";
import { toEntityListQueryFilters } from "@/utils/entityListQueryFilters";
import { normalizeQueueSearch } from "@/utils/queueSearch";
import { useQueueSearch, type QueueListRow } from "@/hooks/useQueueSearch";
import { useTagFilterClick } from "@/hooks/useTagFilterClick";
import type { RejectionCategory } from "@/types/generated/models/RejectionCategory";
import { cleanupExpiredDrafts } from "@/utils/draftStorage";
import { useDockState } from "@/hooks/useDockState";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { canShowSplitPaneCenter, useViewportWidth } from "@/hooks/useSplitPaneCenter";
import { useColumnNavigation } from "@/hooks/useColumnNavigation";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { findTimelineItem, mapItemTypeToDockType } from "@/utils/timelineUtils";
import { getTimelineItems, getTimelineItemProperty } from "@/utils/timelineHelpers";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { FilterState } from "@/types/filters";
import type { TimelineItemType } from '@/types/drafts';
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { alertStatusToUIState, priorityToUIPriority, uiStateToAlertStatus, type UIState } from "@/utils/statusHelpers";
import { getApiErrorMessage } from "@/utils/entityBulkActions";
import { NotFoundError } from "@/pages/NotFoundError";

const ALERT_SORT_OPTIONS = [
  {
    value: "created_at",
    label: "Created",
    directionLabel: { desc: "Newest first", asc: "Oldest first" },
  },
  {
    value: "updated_at",
    label: "Updated",
    directionLabel: { desc: "Recently updated", asc: "Least recently updated" },
  },
  {
    value: "priority",
    label: "Priority",
    directionLabel: { desc: "Highest priority", asc: "Lowest priority" },
  },
  {
    value: "status",
    label: "Status",
    directionLabel: { desc: "Status Z-A", asc: "Status A-Z" },
  },
];

/**
 * Alerts page component for displaying and managing security alerts.
 *
 * Features:
 * - Three-column responsive layout (list, timeline, dock)
 * - Displays paginated list of alerts from the API
 * - Allows clicking alerts to view detailed information
 * - Uses TanStack Query for efficient data fetching with automatic caching and request deduplication
 * - Handles loading and error states gracefully
 * - Supports filtering alerts by status
 * - Mobile-friendly with single-column navigation
 *
 * State Management:
 * - Server state (alerts data): Managed by TanStack Query via useAlerts and useAlertDetail hooks
 * - UI state (selectedAlertId, mobileView): Local React state for tracking selection and mobile navigation
 *
 * @returns The Alerts page component
 */
function Alerts() {
  const { showToast } = useToast();
  // Get URL parameters and navigation
  const { humanId } = useParams<{ humanId?: string }>();
  const location = useLocation();
  const navigate = useViewTransitionNavigate();

  // Get current authenticated user from session context
  const { user, isAuditor } = useSession();
  const currentUser = user?.username || null;

  // UI state for filtering - synced with URL query params
  // Default status to ['NEW', 'IN_PROGRESS'] to show active work for analysts
  const { filters, setFilters, setSearch, currentPage, setCurrentPage } = useURLFilters<FilterState>({
    queue: "alerts",
    userId: user?.id,
    defaults: {
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
      sortBy: "created_at",
      sortOrder: "desc",
    },
  });
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const handleFilterByTag = useTagFilterClick(filters, setFilters);
  const [bulkDialog, setBulkDialog] = useState<'create_case' | 'duplicate' | null>(null);
  const [isBulkCaseSelectorOpen, setIsBulkCaseSelectorOpen] = useState(false);
  const [bulkCaseTitle, setBulkCaseTitle] = useState('');
  const [bulkCaseDescription, setBulkCaseDescription] = useState('');
  const [acceptRecommendationError, setAcceptRecommendationError] = useState<string | null>(null);

  // Alerts can move independently between queue, timeline, and dock on mobile.
  const [mobileColumns, setMobileColumns] = useState<VisibleColumns>(() => humanId ? 'center' : 'left');
  const [alertListWidth, setAlertListWidth] = useState<number>(() => getPersistedWidth(768));

  // Right Dock state for three-column layout (with automatic persistence per alert)
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
  } = useDockState(selectedAlertId);

  // Track newly created item for auto-scrolling (works with any sort order)
  const [scrollToItemId, setScrollToItemId] = useState<string | null>(null);
  
  // Track active reply parent ID from AlertTimeline for RightDock
  const [replyParentId, setReplyParentId] = useState<string | null>(null);

  // Reactive breakpoint state and column navigation helpers
  const breakpoint = useBreakpoint();
  const viewportWidth = useViewportWidth();
  const showSplitCenter = canShowSplitPaneCenter(viewportWidth, alertListWidth, breakpoint);
  const { switchToColumnOnMobile } = useColumnNavigation(setMobileColumns);

  // Initialize selectedAlertId from URL parameter if present
  useEffect(() => {
    if (humanId) {
      const numericId = convertHumanIdToNumeric(humanId);
      if (numericId !== null) {
        setSelectedAlertId(numericId);

        if (breakpoint === 'mobile') setMobileColumns('center');
      }
    } else {
      // No humanId in URL - clear selected alert
      setSelectedAlertId(null);
      setMobileColumns('left');
    }
  }, [humanId, breakpoint]);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch alerts list from API with TanStack Query (automatic caching, retries, and deduplication)
  const pageSize = 50;
  const searchQuery = normalizeQueueSearch(filters.search);
  const queue = useAlerts({
    ...toEntityListQueryFilters(filters),
    search: null,
    enabled: !searchQuery,
    page: currentPage,
    size: pageSize,
  });
  const searchedQueue = useQueueSearch("alert", filters, currentPage, pageSize);
  const { data: alertsData, isLoading, error } = searchQuery ? searchedQueue : queue;
  const bulk = useEntityBulkActions("alert", alertsData?.items, {
    enabled: !isAuditor, users, currentUser, usersLoading: isLoadingUsers, showSplitCenter, selectionScope: searchQuery,
  });
  const bulkSelectedIds = bulk.ids;

  // Fetch selected alert details from API (only when an alert is selected)
  // TanStack Query automatically cancels previous requests when selectedAlertId changes
  // Include linked timelines to embed case/task timeline items as nested source_timeline_items
  const {
    data: alertDetail,
    isLoading: isLoadingDetail,
    error: detailError,
  } = useAlertDetail(selectedAlertId, { includeLinkedTimelines: true });
  useDocumentTitle(
    humanId ? formatEntityTitle(alertDetail?.human_id ?? humanId, alertDetail?.title) : "Alerts"
  );
  const isAlertReadOnly = isAuditor || alertDetail?.status === 'ESCALATED' || !!alertDetail?.case_id;

  // Check if the error is a 404 (only relevant when an alert is selected)
  const is404Error = selectedAlertId && detailError && (
    (detailError as any)?.status === 404 ||
    (detailError as any)?.response?.status === 404 ||
    detailError.message?.includes('404') ||
    detailError.message?.includes('not found')
  );

  // Alert update mutation for assignment operations
  const updateAlertMutation = useUpdateAlert(selectedAlertId, {
    onError: (error) => {
      console.error("Failed to update alert:", error);
    },
  });

  // Triage mutation for escalation
  const triageAlertMutation = useTriageAlert(selectedAlertId, {
    onSuccess: (data) => {
      if (data.case_id) {
        // Construct human ID for case (CAS-0000123)
        const caseHumanId = `CAS-${String(data.case_id).padStart(7, '0')}`;
        navigate(`/cases/${caseHumanId}`);
      }
    },
    onError: (error) => {
      console.error("Failed to escalate alert:", error);
    },
  });

  // Timeline item mutations
  const updateTimelineItemMutation = useUpdateTimelineItem(selectedAlertId, 'alert', {
    onError: (error) => {
      console.error("Failed to update timeline item:", error);
    },
  });

  const deleteTimelineItemMutation = useDeleteTimelineItem(selectedAlertId, 'alert', {
    onError: (error) => {
      console.error("Failed to delete timeline item:", error);
    },
  });

  // Quick terminal mutation for rapid note creation
  const quickTerminalMutation = useQuickTerminalSubmit({
    entityId: selectedAlertId,
    entityType: "alert"
  });

  // Case selector modal state
  const [isCaseSelectorOpen, setIsCaseSelectorOpen] = useState(false);

  // Link alert to case mutation
  const linkAlertToCaseMutation = useLinkAlertToCase(selectedAlertId, {
    onSuccess: (data) => {
      setIsCaseSelectorOpen(false);
      if (data.case_id) {
        // Navigate to the linked case
        const caseHumanId = `CAS-${String(data.case_id).padStart(7, '0')}`;
        navigate(`/cases/${caseHumanId}`);
      }
    },
    onError: (error) => {
      console.error("Failed to link alert to case:", error);
    },
  });

  // Unlink alert from case mutation
  const unlinkAlertFromCaseMutation = useUnlinkAlertFromCase(selectedAlertId, {
    onError: (error) => {
      console.error("Failed to unlink alert from case:", error);
    },
  });

  const bulkAlertActionMutation = useBulkAlertAction({
    onSuccess: (data) => {
      bulk.clear();
      setBulkDialog(null);
      setIsBulkCaseSelectorOpen(false);
      if (data.case_human_id) {
        navigate(`/cases/${data.case_human_id}`);
      }
    },
    onError: (error) => {
      console.error("Failed to apply bulk alert action:", error);
    },
  });

  // Triage recommendation mutations
  const acceptTriageRecommendationMutation = useAcceptTriageRecommendation(selectedAlertId, {
    onSuccess: (data) => {
      setAcceptRecommendationError(null);
      // If a case was created, navigate to it
      if (data.case_human_id) {
        navigate(`/cases/${data.case_human_id}`);
      }
    },
    onError: (error) => {
      console.error("Failed to accept triage recommendation:", error);
      setAcceptRecommendationError(getApiErrorMessage(error, "Failed to accept triage recommendation"));
    },
  });

  const rejectTriageRecommendationMutation = useRejectTriageRecommendation(selectedAlertId, {
    onError: (error) => {
      console.error("Failed to reject triage recommendation:", error);
    },
  });

  // Feature flags for AI triage
  const { data: featureFlags } = useFeatureFlags();
  const isTriageEnabled = featureFlags?.ai_triage_enabled ?? false;

  // Enqueue triage mutation (for retry and manual request)
  const enqueueTriageMutation = useEnqueueTriage(selectedAlertId, {
    onError: (error) => {
      showToast("Could not start AI triage", getApiErrorMessage(error, "Failed to enqueue triage"), "error");
    },
  });


  // Calculate pagination metadata
  const totalPages = alertsData?.pages || 1;

  // Handle page changes with scroll to top
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setCurrentPage(newPage);
    // Scroll to top of alert list
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Clean up expired drafts on page load
  useEffect(() => {
    const cleanedCount = cleanupExpiredDrafts();
    if (cleanedCount > 0) {
      console.log(`Cleaned up ${cleanedCount} expired draft(s)`);
    }
  }, []); // Run once on mount

  // Auto-scroll to newly created timeline item by ID
  useAutoScroll({
    elementId: scrollToItemId,
    idPrefix: 'timeline-item-',
    enabled: !!alertDetail,
    onScrollComplete: () => setScrollToItemId(null),
    onScrollFailed: () => setScrollToItemId(null),
  });

  // Assignment handler functions
  const handleAssignToMe = () => {
    if (!selectedAlertId || !currentUser) return;
    
    // If alert is currently "NEW", change status to "IN_PROGRESS" when assigning
    const updates: { assignee: string; status?: AlertStatus } = { assignee: currentUser };
    if (alertDetail?.status === 'NEW') {
      updates.status = 'IN_PROGRESS';
    }
    
    updateAlertMutation.mutate(updates);
  };

  const handleAssignToUser = (username: string) => {
    if (!selectedAlertId) return;
    
    // If alert is currently "NEW", change status to "IN_PROGRESS" when assigning
    const updates: { assignee: string; status?: AlertStatus } = { assignee: username };
    if (alertDetail?.status === 'NEW') {
      updates.status = 'IN_PROGRESS';
    }
    
    updateAlertMutation.mutate(updates);
  };

  const handleUnassign = () => {
    if (!selectedAlertId) return;
    updateAlertMutation.mutate({ assignee: null });
  };

  // Alert status handler functions
  const handleCloseAlert = (status: UIState) => {
    if (!selectedAlertId) return;
    // Convert UI status (lowercase) to API status (UPPERCASE)
    const apiStatus = uiStateToAlertStatus(status);
    updateAlertMutation.mutate({ status: apiStatus });
  };

  const handleReopenAlert = () => {
    if (!selectedAlertId) return;
    updateAlertMutation.mutate({ status: "IN_PROGRESS" });
  };

  const handleEscalate = () => {
    if (!selectedAlertId || !alertDetail) return;
    
    triageAlertMutation.mutate({
      status: 'ESCALATED',
      escalate_to_case: true,
      case_title: alertDetail.title,
      case_description: alertDetail.description || undefined,
    });
  };

  // Link to case handler - opens the case selector modal
  const handleLinkToCase = () => {
    setIsCaseSelectorOpen(true);
  };

  // Unlink from case handler
  const handleUnlinkFromCase = () => {
    if (!selectedAlertId) return;
    unlinkAlertFromCaseMutation.mutate();
  };

  // Handler for selecting a case in the modal
  const handleSelectCase = (caseId: number) => {
    linkAlertToCaseMutation.mutate(caseId);
  };

  const handleBulkLinkToCase = (caseId: number) => {
    bulkAlertActionMutation.mutate({
      alert_ids: bulkSelectedIds,
      action: 'link_case',
      case_id: caseId,
    });
  };

  const handleBulkCreateCaseSubmit = () => {
    bulkAlertActionMutation.mutate({
      alert_ids: bulkSelectedIds,
      action: 'create_case',
      case_title: bulkCaseTitle.trim(),
      case_description: bulkCaseDescription.trim() || null,
    });
  };

  const handleBulkDuplicateTargetSelect = (target: DuplicateTargetSelection) => {
    bulkAlertActionMutation.mutate({
      alert_ids: bulkSelectedIds,
      action: 'close_duplicate',
      duplicate_target_case_id: target.type === 'case' ? target.id : null,
      duplicate_target_alert_id: target.type === 'alert' ? target.id : null,
    });
  };

  // Tag update handler
  const handleUpdateTags = (tags: string[]) => {
    if (!selectedAlertId) return;
    updateAlertMutation.mutate({ tags });
  };

  // Triage recommendation handlers
  const handleAcceptTriageRecommendation = (options: import('@/types/generated/models/AcceptRecommendationRequest').AcceptRecommendationRequest) => {
    if (!selectedAlertId) return;
    setAcceptRecommendationError(null);
    acceptTriageRecommendationMutation.mutate(options);
  };

  const handleRejectTriageRecommendation = (category: RejectionCategory, reason?: string) => {
    if (!selectedAlertId) return;
    rejectTriageRecommendationMutation.mutate({ category, reason: reason || null });
  };

  const handleRequestTriage = () => {
    if (!selectedAlertId) return;
    enqueueTriageMutation.mutate();
  };

  const handleRetryTriage = () => {
    if (!selectedAlertId) return;
    enqueueTriageMutation.mutate();
  };

  const handleScrollToTimelineItem = (itemId: string) => {
    setScrollToItemId(itemId);
  };

  const handleNavigateToCase = (caseHumanId: string) => {
    navigate(`/cases/${caseHumanId}`);
  };

  // Timeline item handler functions
  const handleFlagItem = (itemId: string) => {
    if (!selectedAlertId || !alertDetail) return;

    const currentFlagged = getTimelineItemProperty(alertDetail, itemId, 'flagged');
    updateTimelineItemMutation.mutate({
      itemId,
      updates: { flagged: !currentFlagged },
    });
  };

  const handleHighlightItem = (itemId: string) => {
    if (!selectedAlertId || !alertDetail) return;

    const currentHighlighted = getTimelineItemProperty(alertDetail, itemId, 'highlighted');
    updateTimelineItemMutation.mutate({
      itemId,
      updates: { highlighted: !currentHighlighted },
    });
  };

  // Handle timeline item edit - opens RightDock in edit mode with pre-populated data
  const handleEditItem = (itemId: string) => {
    if (!selectedAlertId || !alertDetail) return;

    // Find the item using utility function
    const timelineItems = getTimelineItems(alertDetail);
    const itemToEdit = timelineItems ? findTimelineItem(timelineItems, itemId) : null;

    if (itemToEdit && itemToEdit.type) {
      // Map backend type to dock type using utility function
      const dockType = mapItemTypeToDockType(itemToEdit.type);

      // Open dock in edit mode with the item data
      openDockForEdit(dockType, itemToEdit);

      // On mobile, switch to right column (dock)
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

  // Helper to auto-assign alert to current user if unassigned
  const checkAndAssignToMe = () => {
    if (alertDetail && !alertDetail.assignee && currentUser) {
      const updates: { assignee: string; status?: AlertStatus } = { assignee: currentUser };
      if (alertDetail.status === 'NEW') {
        updates.status = 'IN_PROGRESS';
      }
      updateAlertMutation.mutate(updates);
    }
  };

  // Quick Terminal handlers
  const handleQuickTerminalSubmit = async (noteText: string, parentItemId?: string): Promise<void> => {
    const result = await quickTerminalMutation.mutateAsync({ noteText, parentItemId });
    
    // Auto-assign if needed
    checkAndAssignToMe();

    // Trigger scroll to the newly created item
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
    // Timeline will auto-refresh via TanStack Query invalidation
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
    switchToColumnOnMobile('left');
  };

  // Alert selection handler
  const handleAlertSelect = (alertId: number, humanId: string, { floating }: { floating: boolean }) => {
    bulk.clear();
    setSelectedAlertId(alertId);
    navigate(`/alerts/${humanId}${location.search}`, floating ? { viewTransition: false } : undefined);
    switchToColumnOnMobile('center');
  };

  // Handler for going back to alert list from 404 page
  const handleBackToAlertList = () => {
    setSelectedAlertId(null);
    navigate(`/alerts${location.search}`);
  };

  const isBulkPending = bulk.isPending || bulkAlertActionMutation.isPending;
  const bulkActionButtons = (
    <>
      <Button
        size="small"
        variant="neutral-secondary"
        icon={<Link2 />}
        onClick={() => setIsBulkCaseSelectorOpen(true)}
      >
        Link
      </Button>
      <Button
        size="small"
        variant="neutral-secondary"
        icon={<FolderPlus />}
        onClick={() => setBulkDialog('create_case')}
      >
        New Case
      </Button>
      <Button
        size="small"
        variant="neutral-secondary"
        icon={<Copy />}
        onClick={() => setBulkDialog('duplicate')}
      >
        Duplicate
      </Button>
    </>
  );

  // Show 404 error if alert not found (when viewing a specific alert)
  if (is404Error && !bulk.hasMultiple) {
    return (
      <DefaultPageLayout>
        <NotFoundError
          entityType="alert"
          entityId={humanId}
          onBackToList={handleBackToAlertList}
        />
      </DefaultPageLayout>
    );
  }

  // Main render
  return (
    <DefaultPageLayout priority={bulk.hasMultiple ? undefined : alertDetail?.priority || undefined}>
      <EntityQueueLayout
        searchQuery={searchQuery}
        entityType="alert"
        isMobile={breakpoint === 'mobile'}
        showSplitCenter={showSplitCenter}
        listWidth={alertListWidth}
        onListWidthChange={setAlertListWidth}
        mobileColumns={mobileColumns}
        selectedId={selectedAlertId}
        onSelect={handleAlertSelect}
        selection={bulk.selectionColumns ? {
          columns: bulk.selectionColumns,
          toolbar: { ...bulk.toolbarProps, children: bulkActionButtons, disabled: isBulkPending },
          summary: { ...bulk.summaryProps, disabled: isBulkPending },
        } : undefined}
        renderList={(queueListProps) => (
          <EntityList
            items={alertsData?.items ?? []}
            selectedId={bulk.hasMultiple ? null : selectedAlertId}
            getItemHref={(_id, humanId) => `/alerts/${humanId}${location.search}`}
            {...bulk.listProps}
            {...queueListProps}
            filters={filters}
            onFilterChange={setFilters}
            onSearchChange={setSearch}
            retrySearch={searchQuery ? searchedQueue.refetch : undefined}
            sortOptions={ALERT_SORT_OPTIONS}
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={alertsData?.total}
            onPageChange={handlePageChange}
            alwaysShowPaginator
            isLoading={isLoading}
            error={error}
            users={users}
            usersLoading={isLoadingUsers}
            enableTagFilters
            onTagClick={handleFilterByTag}
            getItemIds={(alert: QueueListRow) => ({ id: alert.id, humanId: alert.human_id })}
            mapItemToCard={(alert: QueueListRow) => ({
              id: alert.human_id,
              title: alert.title,
              description: alert.description || '',
              timestamp: alert.created_at,
              assignee: alert.assignee || 'Unassigned',
              tags: alert.tags || [],
              state: alertStatusToUIState(alert.status as AlertStatus),
              priority: priorityToUIPriority(alert.priority),
            })}
            emptyMessage="No alerts found"
          />
        )}
        detail={
          <UnifiedTimeline
            searchQuery={searchQuery}
            entityDetail={alertDetail ?? null}
            entityType="alert"
            mode={isAlertReadOnly ? 'readonly' : 'editable'}
            selectedEntityId={selectedAlertId}
            currentUser={currentUser}
            isLoading={isLoadingDetail}
            error={detailError}
            users={users}
            usersLoading={isLoadingUsers}
            isUpdating={updateAlertMutation.isPending}
            isOverlayOpen={dockOpen || isCaseSelectorOpen || isBulkCaseSelectorOpen || bulkDialog !== null}
            onFlagItem={handleFlagItem}
            onHighlightItem={handleHighlightItem}
            onEditItem={handleEditItem}
            onDeleteItem={handleDeleteItem}
            onDeleteBatch={handleDeleteBatch}
            onAssignToMe={isAuditor ? undefined : handleAssignToMe}
            onAssignToUser={isAuditor ? undefined : handleAssignToUser}
            onUnassign={isAuditor ? undefined : handleUnassign}
            onCloseEntity={isAuditor ? undefined : handleCloseAlert}
            onReopenEntity={isAuditor ? undefined : handleReopenAlert}
            onLinkToCase={isAuditor ? undefined : handleLinkToCase}
            onUnlinkFromCase={isAuditor ? undefined : handleUnlinkFromCase}
            onOpenEntity={isAuditor ? undefined : handleEscalate}
            onQuickTerminalSubmit={handleQuickTerminalSubmit}
            onSlashCommand={handleSlashCommand}
            onAddNote={handleAddNote}
            onMenuItemSelect={handleMenuItemSelect}
            onPasteFiles={handlePasteFiles}
            isSubmittingNote={quickTerminalMutation.isPending}
            onBackToList={handleBackToList}
            scrollToItemId={scrollToItemId}
            onReplyParentIdChange={setReplyParentId}
            onUpdateTags={isAuditor ? undefined : handleUpdateTags}
            onAcceptTriageRecommendation={isAuditor ? undefined : handleAcceptTriageRecommendation}
            onRejectTriageRecommendation={isAuditor ? undefined : handleRejectTriageRecommendation}
            onScrollToTimelineItem={handleScrollToTimelineItem}
            onNavigateToCase={handleNavigateToCase}
            isAcceptingRecommendation={acceptTriageRecommendationMutation.isPending}
            isRejectingRecommendation={rejectTriageRecommendationMutation.isPending}
            acceptRecommendationError={acceptRecommendationError}
            onRetryTriage={isAuditor ? undefined : handleRetryTriage}
            onRerunTriage={isAuditor ? undefined : (expectedCreatedAt) => {
              enqueueTriageMutation.mutate({ expected_recommendation_created_at: expectedCreatedAt });
            }}
            onRequestTriage={isAuditor ? undefined : handleRequestTriage}
            isEnqueuingTriage={enqueueTriageMutation.isPending}
            isTriageEnabled={isTriageEnabled}
          />
        }
        dock={selectedAlertId !== null ? {
          open: dockOpen,
          content: (
            <RightDock
              alertId={selectedAlertId}
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
          ),
        } : undefined}
      />

      {/* Case Selector Modal */}
      <CaseSelectorModal
        isOpen={isCaseSelectorOpen}
        onClose={() => setIsCaseSelectorOpen(false)}
        onSelectCase={handleSelectCase}
        isLinking={linkAlertToCaseMutation.isPending}
      />

      <CaseSelectorModal
        isOpen={isBulkCaseSelectorOpen}
        onClose={() => setIsBulkCaseSelectorOpen(false)}
        onSelectCase={handleBulkLinkToCase}
        isLinking={bulkAlertActionMutation.isPending}
      />

      {bulkDialog === 'duplicate' ? (
        <DuplicateTargetSelectorModal
          isOpen
          onClose={() => setBulkDialog(null)}
          onSelectTarget={handleBulkDuplicateTargetSelect}
          excludedAlertIds={bulkSelectedIds}
          isSubmitting={bulkAlertActionMutation.isPending}
        />
      ) : null}

      {bulk.dialogProps && <BulkActionModal {...bulk.dialogProps} />}

      <Dialog open={bulkDialog === 'create_case'} onOpenChange={(open) => !open && setBulkDialog(null)}>
        <Dialog.Content className="w-[560px] max-w-[90vw]">
          <div className="flex w-full items-center justify-between border-b border-solid border-neutral-border px-6 py-4">
            <span className="text-heading-3 font-heading-3 text-default-font">Create Case From Alerts</span>
            <Button
              variant="neutral-tertiary"
              size="small"
              icon={<X />}
              onClick={() => setBulkDialog(null)}
            />
          </div>
          <div className="flex w-full flex-col gap-4 px-6 py-4">
            <TextField className="w-full" label="Case Title" helpText="">
              <TextField.Input
                value={bulkCaseTitle}
                onChange={(event) => setBulkCaseTitle(event.target.value)}
                placeholder="Case title"
              />
            </TextField>
            <TextArea className="w-full" label="Description" helpText="">
              <TextArea.Input
                value={bulkCaseDescription}
                onChange={(event) => setBulkCaseDescription(event.target.value)}
                placeholder="Description"
              />
            </TextArea>
          </div>
          <div className="flex w-full items-center justify-end gap-2 border-t border-solid border-neutral-border px-6 py-4">
            <Button variant="neutral-secondary" onClick={() => setBulkDialog(null)}>Cancel</Button>
            <Button
              onClick={handleBulkCreateCaseSubmit}
              disabled={!bulkCaseTitle.trim()}
              loading={bulkAlertActionMutation.isPending}
            >
              Create
            </Button>
          </div>
        </Dialog.Content>
      </Dialog>

    </DefaultPageLayout>
  );
}

export default Alerts;
