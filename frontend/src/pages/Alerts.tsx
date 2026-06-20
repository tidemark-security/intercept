"use client";

import React, { useState, useEffect } from "react";
import { useLocation, useParams } from 'react-router-dom';
import { CheckCircle2, Copy, FolderPlus, Link2, Tags, X } from 'lucide-react';
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { Button } from "@/components/buttons/Button";
import { Select } from "@/components/forms/Select";
import { TagsManager } from "@/components/forms/TagsManager";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { Dialog } from "@/components/overlays/Dialog";
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { ThreeColumnLayout } from "@/components/layout/ThreeColumnLayout";
import { getPersistedWidth } from "@/components/layout/ColumnRail";
import { EntityList } from "@/components/data-display/EntityList";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { RightDock } from '@/components/layout/RightDock';
import { CaseSelectorModal } from "@/components/entities/CaseSelectorModal";
import {
  DuplicateTargetSelectorModal,
  type DuplicateTargetSelection,
} from "@/components/entities/DuplicateTargetSelectorModal";
import { useAlerts } from "@/hooks/useAlerts";
import { useAlertDetail } from "@/hooks/useAlertDetail";
import { convertHumanIdToNumeric } from "@/hooks/useAlertIdFromHumanId";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateAlert } from "@/hooks/useUpdateAlert";
import { useTriageAlert } from "@/hooks/useTriageAlert";
import { useLinkAlertToCase } from "@/hooks/useLinkAlertToCase";
import { useUnlinkAlertFromCase } from "@/hooks/useUnlinkAlertFromCase";
import { useBulkAlertAction } from "@/hooks/useBulkAlertAction";
import { useUpdateTimelineItem } from "@/hooks/useUpdateTimelineItem";
import { useDeleteTimelineItem } from "@/hooks/useDeleteTimelineItem";
import { useQuickTerminalSubmit } from "@/hooks/useQuickTerminalSubmit";
import { useAcceptTriageRecommendation } from "@/hooks/useAcceptTriageRecommendation";
import { useRejectTriageRecommendation } from "@/hooks/useRejectTriageRecommendation";
import { useEnqueueTriage } from "@/hooks/useEnqueueTriage";
import { useFeatureFlags } from "@/hooks/useFeatureFlags";
import { useSession } from "@/contexts/sessionContext";
import { useURLFilters } from "@/hooks/useURLFilters";
import { useTagFilterClick } from "@/hooks/useTagFilterClick";
import type { RejectionCategory } from "@/types/generated/models/RejectionCategory";
import { cleanupExpiredDrafts } from "@/utils/draftStorage";
import { useDockState } from "@/hooks/useDockState";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { useColumnNavigation } from "@/hooks/useColumnNavigation";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { findTimelineItem, mapItemTypeToDockType } from "@/utils/timelineUtils";
import { getTimelineItems, getTimelineItemProperty } from "@/utils/timelineHelpers";
import { getColumnConfig, getInitialVisibleColumns } from "@/utils/columnConfig";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { FilterState } from "@/types/filters";
import type { TimelineItemType } from '@/types/drafts';
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { alertStatusToUIState, priorityToUIPriority, uiStateToAlertStatus, type UIState } from "@/utils/statusHelpers";
import { ALERT_STATUS_OPTIONS } from "@/utils/statusLabels";
import { NotFoundError } from "@/pages/NotFoundError";

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
  // Get URL parameters and navigation
  const { humanId } = useParams<{ humanId?: string }>();
  const location = useLocation();
  const navigate = useViewTransitionNavigate();

  // Get current authenticated user from session context
  const { user, isAuditor } = useSession();
  const currentUser = user?.username || null;

  // UI state for filtering - synced with URL query params
  // Default status to ['NEW', 'IN_PROGRESS'] to show active work for analysts
  const { filters, setFilters, currentPage, setCurrentPage } = useURLFilters<FilterState>({
    defaults: {
      search: "",
      assignee: null,
      status: ["NEW", "IN_PROGRESS"],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
    },
  });
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const handleFilterByTag = useTagFilterClick(filters, setFilters);
  const [bulkSelectedAlertIds, setBulkSelectedAlertIds] = useState<Set<number>>(new Set());
  const [bulkDialog, setBulkDialog] = useState<'status' | 'create_case' | 'duplicate' | 'tags' | null>(null);
  const [isBulkCaseSelectorOpen, setIsBulkCaseSelectorOpen] = useState(false);
  const [bulkStatus, setBulkStatus] = useState<AlertStatus>('IN_PROGRESS');
  const [bulkCaseTitle, setBulkCaseTitle] = useState('');
  const [bulkCaseDescription, setBulkCaseDescription] = useState('');
  const [bulkTags, setBulkTags] = useState<string[]>([]);

  // Column visibility state: controls which columns are visible
  // On mobile (<768px): typically 'left' | 'center' | 'right' for single column
  // On tablet/desktop: typically 'left+center' | 'center+right' based on dock state
  // On ultrawide: typically 'all' for three columns
  const [visibleColumns, setVisibleColumns] = useState<VisibleColumns>(() => getInitialVisibleColumns());
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
  const { switchToColumnOnMobile } = useColumnNavigation(setVisibleColumns);

  // Automatically adjust visible columns based on screen size, dock state, and alert selection
  // This provides responsive behavior while allowing manual override on mobile
  useEffect(() => {
    // If no alert is selected
    if (!selectedAlertId) {
      // On ultrawide, show left+center to display the empty state
      if (breakpoint === 'ultrawide') {
        setVisibleColumns('left+center');
      } else {
        // On other breakpoints, show only left
        setVisibleColumns('left');
      }
      return;
    }

    // On ultrawide, show all columns when dock is open, otherwise left+center
    if (breakpoint === 'ultrawide') {
      setVisibleColumns(dockOpen ? 'all' : 'left+center');
      return;
    }

    // On desktop, keep list + timeline visible so the split pane can resize them.
    // Tablet remains focused on the timeline because the default list width crowds it out.
    if (breakpoint === 'desktop') {
      setVisibleColumns(dockOpen ? 'all' : 'left+center');
      return;
    }

    // On tablet, dock floats as drawer over center column.
    if (breakpoint === 'tablet') {
      setVisibleColumns(dockOpen ? 'center+right' : 'center');
    }
    // On mobile, keep current single column (don't auto-switch)
    // Mobile navigation is handled explicitly by user interactions
  }, [dockOpen, selectedAlertId, breakpoint]);

  // Initialize selectedAlertId from URL parameter if present
  useEffect(() => {
    if (humanId) {
      const numericId = convertHumanIdToNumeric(humanId);
      if (numericId !== null) {
        setSelectedAlertId(numericId);

        // Set appropriate columns based on current breakpoint
        if (breakpoint === 'ultrawide') {
          setVisibleColumns('left+center');
        } else if (breakpoint === 'desktop') {
          setVisibleColumns('left+center');
        } else if (breakpoint === 'tablet') {
          setVisibleColumns('center');
        } else {
          // Mobile: switch to center (timeline) view when alert is selected via URL
          setVisibleColumns('center');
        }
      }
    } else {
      // No humanId in URL - clear selected alert
      setSelectedAlertId(null);
      // Show left+center on ultrawide to display empty state, otherwise just left
      if (breakpoint === 'ultrawide') {
        setVisibleColumns('left+center');
      } else {
        setVisibleColumns('left');
      }
    }
  }, [humanId, breakpoint]);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch alerts list from API with TanStack Query (automatic caching, retries, and deduplication)
  const pageSize = 50;
  const { data: alertsData, isLoading, error } = useAlerts({
    status: filters.status, // Pass array directly, null if no filter
    assignee: filters.assignee,
    startDate: filters.dateRange?.start || null,
    endDate: filters.dateRange?.end || null,
    search: filters.search || null,
    includeTags: filters.includeTags || null,
    excludeTags: filters.excludeTags || null,
    page: currentPage,
    size: pageSize,
  });

  // Fetch selected alert details from API (only when an alert is selected)
  // TanStack Query automatically cancels previous requests when selectedAlertId changes
  // Include linked timelines to embed case/task timeline items as nested source_timeline_items
  const {
    data: alertDetail,
    isLoading: isLoadingDetail,
    error: detailError,
  } = useAlertDetail(selectedAlertId, { includeLinkedTimelines: true });
  const isAlertReadOnly = isAuditor || alertDetail?.status === 'ESCALATED' || !!alertDetail?.case_id;
  const bulkSelectedIds = Array.from(bulkSelectedAlertIds);

  // Check if the error is a 404 (only relevant when an alert is selected)
  const is404Error = selectedAlertId && detailError && (
    (detailError as any)?.status === 404 ||
    (detailError as any)?.response?.status === 404 ||
    detailError.message?.includes('404') ||
    detailError.message?.includes('not found')
  );

  const handleAlertListRailToggle = () => {
    // The alerts split pane is resizable but not collapsible.
  };

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
      setBulkSelectedAlertIds(new Set());
      setBulkDialog(null);
      setBulkTags([]);
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
      // If a case was created, navigate to it
      if (data.case_human_id) {
        navigate(`/cases/${data.case_human_id}`);
      }
    },
    onError: (error) => {
      console.error("Failed to accept triage recommendation:", error);
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
      console.error("Failed to enqueue triage:", error);
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

  const handleBulkSelectionChange = (alertId: number, selected: boolean) => {
    setBulkSelectedAlertIds((previous) => {
      const next = new Set(previous);
      if (selected) {
        next.add(alertId);
      } else {
        next.delete(alertId);
      }
      return next;
    });
  };

  const handleBulkSelectVisible = (selected: boolean, alertIds: number[]) => {
    setBulkSelectedAlertIds((previous) => {
      const next = new Set(previous);
      alertIds.forEach((alertId) => {
        if (selected) {
          next.add(alertId);
        } else {
          next.delete(alertId);
        }
      });
      return next;
    });
  };

  const handleBulkLinkToCase = (caseId: number) => {
    bulkAlertActionMutation.mutate({
      alert_ids: bulkSelectedIds,
      action: 'link_case',
      case_id: caseId,
    });
  };

  const handleBulkStatusSubmit = () => {
    bulkAlertActionMutation.mutate({
      alert_ids: bulkSelectedIds,
      action: 'update_status',
      status: bulkStatus,
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

  const handleBulkTagsSubmit = () => {
    bulkAlertActionMutation.mutate({
      alert_ids: bulkSelectedIds,
      action: 'add_tags',
      tags: bulkTags,
    });
  };

  const handleBulkTagsClose = () => {
    setBulkTags([]);
    setBulkDialog(null);
  };

  // Tag update handler
  const handleUpdateTags = (tags: string[]) => {
    if (!selectedAlertId) return;
    updateAlertMutation.mutate({ tags });
  };

  // Triage recommendation handlers
  const handleAcceptTriageRecommendation = (options: import('@/types/generated/models/AcceptRecommendationRequest').AcceptRecommendationRequest) => {
    if (!selectedAlertId) return;
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
  const handleAlertSelect = (alertId: number, humanId: string) => {
    setSelectedAlertId(alertId);
    navigate(`/alerts/${humanId}${location.search}`);

    // Only change visible columns on mobile - ultrawide/desktop/tablet stay as-is
    switchToColumnOnMobile('center');
    // On ultrawide/desktop/tablet, the resize effect handles visibility
  };

  // Handler for going back to alert list from 404 page
  const handleBackToAlertList = () => {
    setSelectedAlertId(null);
    navigate(`/alerts${location.search}`);
  };

  const bulkActionsPanel = !isAuditor && bulkSelectedIds.length > 1 ? (
    <div className="flex w-full flex-wrap items-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2 shadow-sm">
      <span className="mr-auto text-body-bold font-body-bold text-default-font">
        {bulkSelectedIds.length} selected
      </span>
      <Button
        size="small"
        variant="neutral-secondary"
        icon={<CheckCircle2 />}
        onClick={() => setBulkDialog('status')}
      >
        Status
      </Button>
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
      <Button
        size="small"
        variant="neutral-secondary"
        icon={<Tags />}
        onClick={() => setBulkDialog('tags')}
      >
        Tags
      </Button>
      <Button
        size="small"
        variant="neutral-tertiary"
        icon={<X />}
        onClick={() => setBulkSelectedAlertIds(new Set())}
      />
    </div>
  ) : null;

  // Show 404 error if alert not found (when viewing a specific alert)
  if (is404Error) {
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
    <DefaultPageLayout priority={alertDetail?.priority || undefined}>
      <ThreeColumnLayout
        leftColumn={
          <EntityList
            items={alertsData?.items ?? []}
            selectedId={selectedAlertId}
            onSelect={handleAlertSelect}
            getItemHref={(_id, humanId) => `/alerts/${humanId}${location.search}`}
            selectable={!isAuditor}
            selectedIds={bulkSelectedAlertIds}
            onSelectionChange={handleBulkSelectionChange}
            onSelectVisible={handleBulkSelectVisible}
            toolbarActions={bulkActionsPanel}
            filters={filters}
            onFilterChange={setFilters}
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
            getItemIds={(alert: AlertRead) => ({ id: alert.id, humanId: alert.human_id })}
            mapItemToCard={(alert: AlertRead) => ({
              id: alert.human_id,
              title: alert.title,
              description: alert.description || '',
              timestamp: alert.created_at,
              assignee: alert.assignee || 'Unassigned',
              tags: alert.tags || [],
              state: alertStatusToUIState(alert.status),
              priority: priorityToUIPriority(alert.priority),
            })}
            emptyMessage="No alerts found"
          />
        }
        centerColumn={
          <UnifiedTimeline
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
            onRetryTriage={isAuditor ? undefined : handleRetryTriage}
            onRequestTriage={isAuditor ? undefined : handleRequestTriage}
            isEnqueuingTriage={enqueueTriageMutation.isPending}
            isTriageEnabled={isTriageEnabled}
          />
        }
        rightColumn={
          selectedAlertId !== null ? (
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
          ) : (
            <div />
          )
        }
        visibleColumns={visibleColumns}
        onVisibleColumnsChange={setVisibleColumns}
        columnConfig={getColumnConfig(selectedAlertId, selectedAlertId ? alertListWidth : undefined)}
        dimLeftColumn={!!selectedAlertId}
        showLeftRail={!!selectedAlertId}
        onLeftRailToggle={handleAlertListRailToggle}
        leftColumnWidth={alertListWidth}
        onLeftColumnWidthChange={setAlertListWidth}
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

      <Dialog open={bulkDialog === 'status'} onOpenChange={(open) => !open && setBulkDialog(null)}>
        <Dialog.Content className="w-[520px] max-w-[90vw]">
          <div className="flex w-full items-center justify-between border-b border-solid border-neutral-border px-6 py-4">
            <span className="text-heading-3 font-heading-3 text-default-font">Update Status</span>
            <Button
              variant="neutral-tertiary"
              size="small"
              icon={<X />}
              onClick={() => setBulkDialog(null)}
            />
          </div>
          <div className="w-full px-6 py-4">
            <Select
              className="w-full"
              label="Status"
              placeholder="Select status"
              value={bulkStatus}
              onValueChange={(value) => setBulkStatus(value as AlertStatus)}
            >
              {ALERT_STATUS_OPTIONS.map((option) => (
                <Select.Item key={option.value} value={option.value}>
                  {option.label}
                </Select.Item>
              ))}
            </Select>
          </div>
          <div className="flex w-full items-center justify-end gap-2 border-t border-solid border-neutral-border px-6 py-4">
            <Button variant="neutral-secondary" onClick={() => setBulkDialog(null)}>Cancel</Button>
            <Button onClick={handleBulkStatusSubmit} loading={bulkAlertActionMutation.isPending}>
              Apply
            </Button>
          </div>
        </Dialog.Content>
      </Dialog>

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

      <Dialog open={bulkDialog === 'tags'} onOpenChange={(open) => !open && handleBulkTagsClose()}>
        <Dialog.Content className="w-[520px] max-w-[90vw]">
          <div className="flex w-full items-center justify-between border-b border-solid border-neutral-border px-6 py-4">
            <span className="text-heading-3 font-heading-3 text-default-font">Add Tags</span>
            <Button
              variant="neutral-tertiary"
              size="small"
              icon={<X />}
              onClick={handleBulkTagsClose}
            />
          </div>
          <div className="w-full px-6 py-4">
            <TagsManager
              tags={bulkTags}
              onTagsChange={setBulkTags}
              label="Tags"
              placeholder="Enter tags and press Enter"
              className="w-full"
            />
          </div>
          <div className="flex w-full items-center justify-end gap-2 border-t border-solid border-neutral-border px-6 py-4">
            <Button variant="neutral-secondary" onClick={handleBulkTagsClose}>Cancel</Button>
            <Button
              onClick={handleBulkTagsSubmit}
              disabled={bulkTags.length === 0}
              loading={bulkAlertActionMutation.isPending}
            >
              Add
            </Button>
          </div>
        </Dialog.Content>
      </Dialog>

    </DefaultPageLayout>
  );
}

export default Alerts;
