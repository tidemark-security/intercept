"use client";

import React, { useState } from "react";
import { useLocation } from "react-router-dom";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { EntityQueueLayout } from "@/components/layout/EntityQueueLayout";
import { getPersistedWidth } from "@/components/layout/ColumnRail";
import { EntityList } from "@/components/data-display/EntityList";
import { BulkActionModal } from "@/components/entities/BulkActionModal";
import { useEntityBulkActions } from "@/hooks/useEntityBulkActions";
import { Button } from "@/components/buttons/Button";
import { CreateCaseModal } from "@/components/entities/CreateCaseModal";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { useCreateCase } from "@/hooks/useCreateCase";
import { useCases } from "@/hooks/useCases";
import { useCaseDetail } from "@/hooks/useCaseDetail";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateCase } from "@/hooks/useUpdateCase";
import { useSession } from "@/contexts/sessionContext";
import { useToast } from "@/contexts/ToastContext";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { canShowSplitPaneCenter, useViewportWidth } from "@/hooks/useSplitPaneCenter";
import { useURLFilters } from "@/hooks/useURLFilters";
import { toEntityListQueryFilters } from "@/utils/entityListQueryFilters";
import { normalizeQueueSearch } from "@/utils/queueSearch";
import { useQueueSearch, type QueueListRow } from "@/hooks/useQueueSearch";
import { useTagFilterClick } from "@/hooks/useTagFilterClick";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { CaseFilterState } from "@/types/filters";
import { caseStatusToUIState, priorityToUIPriority } from "@/utils/statusHelpers";
import { CASE_STATUS_OPTIONS } from "@/utils/statusLabels";
import { Plus } from "lucide-react";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

const CASE_SORT_OPTIONS = [
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
 * Cases List Page - Browse and filter cases with optional preview
 * 
 * Features:
 * - Paginated case list with filters
 * - Read-only timeline preview in center column (when case selected)
 * - On mobile: tapping a case navigates to detail page
 * - On non-mobile: preview beside or floating over the case list
 * 
 * @returns The Cases List page component
 */
function CasesListPage() {
  useDocumentTitle("Cases");
  const navigate = useViewTransitionNavigate();
  const location = useLocation();
  const { user, isAuditor } = useSession();
  const { showToast } = useToast();
  const currentUser = user?.username || null;

  // UI state for filtering - synced with URL query params
  const { filters, setFilters, setSearch, currentPage, setCurrentPage } = useURLFilters<CaseFilterState>({
    queue: "cases",
    userId: user?.id,
    defaults: {
      search: "",
      assignee: null,
      status: ["NEW" as CaseStatus, "IN_PROGRESS" as CaseStatus],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
      sortBy: "created_at",
      sortOrder: "desc",
    },
  });
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const handleFilterByTag = useTagFilterClick(filters, setFilters);
  const [isCreateCaseModalOpen, setIsCreateCaseModalOpen] = useState(false);
  const [createCaseError, setCreateCaseError] = useState<string | null>(null);

  const [caseListWidth, setCaseListWidth] = useState<number>(() => getPersistedWidth(768));

  // Reactive breakpoint state
  const breakpoint = useBreakpoint();
  const viewportWidth = useViewportWidth();
  const showSplitCenter = canShowSplitPaneCenter(viewportWidth, caseListWidth, breakpoint);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch cases list from API
  const pageSize = 50;
  const searchQuery = normalizeQueueSearch(filters.search);
  const queue = useCases({
    ...toEntityListQueryFilters(filters),
    search: null,
    enabled: !searchQuery,
    page: currentPage,
    size: pageSize,
  });
  const searchedQueue = useQueueSearch("case", filters, currentPage, pageSize);
  const { data: casesData, isLoading, error } = searchQuery ? searchedQueue : queue;
  const bulk = useEntityBulkActions("case", casesData?.items, {
    enabled: !isAuditor, users, currentUser, usersLoading: isLoadingUsers, showSplitCenter, selectionScope: searchQuery,
  });

  // Fetch selected case details from API (only when a case is selected)
  const {
    data: caseDetail,
    isLoading: isLoadingDetail,
    error: detailError,
  } = useCaseDetail(selectedCaseId);

  // Case update mutation (for assignment in preview mode)
  const updateCaseMutation = useUpdateCase(selectedCaseId, {
    onError: (error) => {
      console.error("Failed to update case:", error);
    },
  });

  const createCaseMutation = useCreateCase({
    onSuccess: (createdCase) => {
      setCreateCaseError(null);
      setIsCreateCaseModalOpen(false);
      navigate(`/cases/${createdCase.human_id}`);
    },
    onError: (error) => {
      setCreateCaseError(error.message || 'Failed to create case');
    },
  });

  // Calculate pagination metadata
  const totalPages = casesData?.pages || 1;

  // Handle page changes
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setCurrentPage(newPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Assignment handler functions (for preview mode)
  const handleAssignToMe = () => {
    if (!selectedCaseId || !currentUser) return;
    updateCaseMutation.mutate({ assignee: currentUser });
  };

  const handleAssignToUser = (username: string) => {
    if (!selectedCaseId) return;
    updateCaseMutation.mutate({ assignee: username });
  };

  const handleUnassign = () => {
    if (!selectedCaseId) return;
    updateCaseMutation.mutate({ assignee: null });
  };

  // Case selection handler
  const handleCaseSelect = (caseId: number, caseHumanId: string) => {
    bulk.clear();
    if (breakpoint === 'mobile') {
      navigate(`/cases/${caseHumanId}${location.search}`);
    } else {
      setSelectedCaseId(caseId);
    }
  };

  // Double-click handler - always navigate to detail view
  const handleCaseDoubleClick = (caseId: number, caseHumanId: string) => {
    navigate(`/cases/${caseHumanId}${location.search}`);
  };

  // Handle "Open Case" from timeline to navigate to detail view
  const handleOpenCase = () => {
    if (caseDetail?.human_id) {
      navigate(`/cases/${caseDetail.human_id}${location.search}`);
    }
  };

  // Handle back to list (for mobile only)
  const handleBackToList = () => {
    setSelectedCaseId(null);
  };

  const handleCreateCase = async (payload: {
    title: string;
    description: string;
    priority: CaseRead["priority"];
    assignee: string | null;
    tags: string[];
  }) => {
    setCreateCaseError(null);
    try {
      await createCaseMutation.mutateAsync({
        title: payload.title,
        description: payload.description,
        priority: payload.priority,
        assignee: payload.assignee,
        tags: payload.tags,
      });
    } catch {
      // Error state is handled by mutation onError callback
    }
  };
  return (
    <DefaultPageLayout priority={bulk.hasMultiple ? undefined : caseDetail?.priority || undefined}>
      <EntityQueueLayout
        searchQuery={searchQuery}
        entityType="case"
        isMobile={breakpoint === 'mobile'}
        showSplitCenter={showSplitCenter}
        selectedId={selectedCaseId}
        listWidth={caseListWidth}
        onListWidthChange={setCaseListWidth}
        onSelect={handleCaseSelect}
        selection={bulk.selectionColumns ? {
          columns: bulk.selectionColumns,
          toolbar: bulk.toolbarProps,
          summary: bulk.summaryProps,
        } : undefined}
        renderList={(queueListProps) => (
          <EntityList
            items={casesData?.items ?? []}
            selectedId={bulk.hasMultiple ? null : selectedCaseId}
            {...bulk.listProps}
            {...queueListProps}
            onDoubleClick={handleCaseDoubleClick}
            getItemHref={(_id, humanId) => `/cases/${humanId}${location.search}`}
            filters={filters}
            onFilterChange={setFilters}
            onSearchChange={setSearch}
            retrySearch={searchQuery ? searchedQueue.refetch : undefined}
            enableTagFilters
            onTagClick={handleFilterByTag}
            statusOptions={CASE_STATUS_OPTIONS}
            sortOptions={CASE_SORT_OPTIONS}
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={casesData?.total}
            onPageChange={handlePageChange}
            alwaysShowPaginator
            paginatorCenterContent={
              <Button
                variant="brand-primary"
                size="medium"
                icon={<Plus />}
                onClick={() => setIsCreateCaseModalOpen(true)}
              >
                Create New Case
              </Button>
            }
            isLoading={isLoading}
            error={error}
            users={users}
            usersLoading={isLoadingUsers}
            getItemIds={(caseItem: QueueListRow) => ({ id: caseItem.id, humanId: caseItem.human_id })}
            mapItemToCard={(caseItem: QueueListRow) => ({
              id: caseItem.human_id,
              title: caseItem.title,
              description: caseItem.description || '',
              timestamp: caseItem.created_at,
              assignee: caseItem.assignee || 'Unassigned',
              tags: caseItem.tags || [],
              state: caseStatusToUIState(caseItem.status as CaseStatus),
              priority: priorityToUIPriority(caseItem.priority),
            })}
            emptyMessage="No cases found"
          />
        )}
        detail={
          <UnifiedTimeline
            searchQuery={searchQuery}
            entityDetail={caseDetail ?? null}
            entityType="case"
            selectedEntityId={selectedCaseId}
            currentUser={currentUser}
            isLoading={isLoadingDetail}
            error={detailError}
            users={users}
            usersLoading={isLoadingUsers}
            isUpdating={updateCaseMutation.isPending}
            mode="readonly"
            onAssignToMe={handleAssignToMe}
            onAssignToUser={handleAssignToUser}
            onUnassign={handleUnassign}
            onBackToList={handleBackToList}
            onOpenEntity={handleOpenCase}
          />
        }
      />
      {bulk.dialogProps && <BulkActionModal {...bulk.dialogProps} />}

      <CreateCaseModal
        open={isCreateCaseModalOpen}
        onOpenChange={(open) => {
          setIsCreateCaseModalOpen(open);
          if (!open) {
            setCreateCaseError(null);
          }
        }}
        isSubmitting={createCaseMutation.isPending}
        submitError={createCaseError}
        onSubmit={handleCreateCase}
      />
    </DefaultPageLayout>
  );
}

export default CasesListPage;
