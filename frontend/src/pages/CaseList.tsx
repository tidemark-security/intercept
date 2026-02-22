"use client";

import React, { useState, useEffect } from "react";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { ThreeColumnLayout } from "@/components/layout/ThreeColumnLayout";
import { EntityList } from "@/components/data-display/EntityList";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { useCases } from "@/hooks/useCases";
import { useCaseDetail } from "@/hooks/useCaseDetail";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateCase } from "@/hooks/useUpdateCase";
import { useSession } from "@/contexts/sessionContext";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { useURLFilters } from "@/hooks/useURLFilters";
import { getColumnConfig, getInitialVisibleColumns } from "@/utils/columnConfig";
import type { CaseStatus } from "@/types/generated/models/CaseStatus";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { CaseFilterState } from "@/types/filters";
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { caseStatusToUIState, priorityToUIPriority } from "@/utils/statusHelpers";

/**
 * Cases List Page - Browse and filter cases with optional preview
 * 
 * Features:
 * - Paginated case list with filters
 * - Read-only timeline preview in center column (when case selected)
 * - On mobile: tapping a case navigates to detail page
 * - On non-mobile: case list always visible with side-by-side preview
 * 
 * @returns The Cases List page component
 */
function CasesListPage() {
  const navigate = useViewTransitionNavigate();
  const { user } = useSession();
  const currentUser = user?.username || null;

  // UI state for filtering - synced with URL query params
  const { filters, setFilters, currentPage, setCurrentPage } = useURLFilters<CaseFilterState>({
    defaults: {
      search: "",
      assignee: null,
      status: ["NEW" as CaseStatus, "IN_PROGRESS" as CaseStatus],
      dateRange: null,
    },
  });
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);

  // Column visibility state
  const [visibleColumns, setVisibleColumns] = useState<VisibleColumns>(() => getInitialVisibleColumns());

  // Reactive breakpoint state
  const breakpoint = useBreakpoint();

  // Automatically adjust visible columns based on selection and screen size
  useEffect(() => {
    if (!selectedCaseId) {
      // On ultrawide, show left+center to display the empty state
      if (breakpoint === 'ultrawide') {
        setVisibleColumns('left+center');
      } else {
        setVisibleColumns('left');
      }
    } else {
      if (breakpoint === 'ultrawide') {
        setVisibleColumns('left+center');
      } else if (breakpoint === 'desktop' || breakpoint === 'tablet') {
        // Always keep left column visible on non-mobile breakpoints
        setVisibleColumns('left+center');
      }
      // Mobile: keep current single column
    }
  }, [selectedCaseId, breakpoint]);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch cases list from API
  const pageSize = 50;
  const { data: casesData, isLoading, error } = useCases({
    status: filters.status || null,
    assignee: filters.assignee?.[0] || null,
    search: filters.search || null,
    startDate: filters.dateRange?.start || null,
    endDate: filters.dateRange?.end || null,
    page: currentPage,
    size: pageSize,
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
    setSelectedCaseId(caseId);
    
    if (breakpoint === 'mobile') {
      // On mobile, navigate to detail view
      navigate(`/cases/${caseHumanId}`);
    } else {
      // On non-mobile, stay in list view and show read-only timeline
      // (visibleColumns will be updated by useEffect)
    }
  };

  // Double-click handler - always navigate to detail view
  const handleCaseDoubleClick = (caseId: number, caseHumanId: string) => {
    navigate(`/cases/${caseHumanId}`);
  };

  // Handle "Open Case" from timeline to navigate to detail view
  const handleOpenCase = () => {
    if (caseDetail?.human_id) {
      navigate(`/cases/${caseDetail.human_id}`);
    }
  };

  // Handle back to list (for mobile only)
  const handleBackToList = () => {
    setSelectedCaseId(null);
    setVisibleColumns('left');
  };

  return (
    <DefaultPageLayout priority={caseDetail?.priority || undefined}>
      <ThreeColumnLayout
        leftColumn={
          <EntityList
            items={casesData?.items ?? []}
            selectedId={selectedCaseId}
            onSelect={handleCaseSelect}
            onDoubleClick={handleCaseDoubleClick}
            getItemHref={(_id, humanId) => `/cases/${humanId}`}
            filters={filters}
            onFilterChange={setFilters}
            statusOptions={[
              { value: 'NEW', label: 'New' },
              { value: 'IN_PROGRESS', label: 'In Progress' },
              { value: 'CLOSED', label: 'Closed' },
            ]}
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={casesData?.total}
            onPageChange={handlePageChange}
            isLoading={isLoading}
            error={error}
            users={users}
            usersLoading={isLoadingUsers}
            getItemIds={(caseItem: CaseRead) => ({ id: caseItem.id, humanId: caseItem.human_id })}
            mapItemToCard={(caseItem: CaseRead) => ({
              id: caseItem.human_id,
              title: caseItem.title,
              description: caseItem.description || '',
              timestamp: caseItem.created_at,
              assignee: caseItem.assignee || 'Unassigned',
              tags: caseItem.tags || '',
              state: caseStatusToUIState(caseItem.status),
              priority: priorityToUIPriority(caseItem.priority),
            })}
            emptyMessage="No cases found"
          />
        }
        centerColumn={
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
            mode="readonly"
            onAssignToMe={handleAssignToMe}
            onAssignToUser={handleAssignToUser}
            onUnassign={handleUnassign}
            onBackToList={handleBackToList}
            onOpenEntity={handleOpenCase}
          />
        }
        rightColumn={<div></div>}
        visibleColumns={visibleColumns}
        onVisibleColumnsChange={setVisibleColumns}
        columnConfig={getColumnConfig(selectedCaseId)}
        dimLeftColumn={!!selectedCaseId}
      />
    </DefaultPageLayout>
  );
}

export default CasesListPage;
