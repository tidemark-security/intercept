"use client";

import React, { useState, useEffect } from "react";
import { useViewTransitionNavigate } from '@/hooks/useViewTransitionNavigate';
import { DefaultPageLayout } from "@/components/layout/DefaultPageLayout";
import { ThreeColumnLayout } from "@/components/layout/ThreeColumnLayout";
import { EntityList } from "@/components/data-display/EntityList";
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { useTasks } from "@/hooks/useTasks";
import { useTaskDetail } from "@/hooks/useTaskDetail";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateTask } from "@/hooks/useUpdateTask";
import { useSession } from "@/contexts/sessionContext";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { useURLFilters } from "@/hooks/useURLFilters";
import { getColumnConfig, getInitialVisibleColumns } from "@/utils/columnConfig";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import type { TaskFilterState } from "@/types/filters";
import type { VisibleColumns } from '@/components/layout/ThreeColumnLayout.types';
import { taskStatusToUIState, priorityToUIPriority, taskStateToMenuCardState } from "@/utils/statusHelpers";

/**
 * Tasks List Page - Browse and filter tasks with optional preview
 * 
 * Features:
 * - Paginated task list with filters
 * - Read-only timeline preview in center column (when task selected)
 * - On mobile: tapping a task navigates to detail page
 * - On non-mobile: task list always visible with side-by-side preview
 * 
 * @returns The Tasks List page component
 */
function TasksListPage() {
  const navigate = useViewTransitionNavigate();
  const { user } = useSession();
  const currentUser = user?.username || null;

  // UI state for filtering - synced with URL query params
  const { filters, setFilters, currentPage, setCurrentPage } = useURLFilters<TaskFilterState>({
    defaults: {
      search: "",
      assignee: null,
      status: ["TODO" as TaskStatus, "IN_PROGRESS" as TaskStatus],
      dateRange: null,
    },
  });
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);

  // Column visibility state
  const [visibleColumns, setVisibleColumns] = useState<VisibleColumns>(() => getInitialVisibleColumns());

  // Reactive breakpoint state
  const breakpoint = useBreakpoint();

  // Automatically adjust visible columns based on selection and screen size
  useEffect(() => {
    if (!selectedTaskId) {
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
  }, [selectedTaskId, breakpoint]);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch tasks list from API
  const pageSize = 50;
  const { data: tasksData, isLoading, error } = useTasks({
    status: filters.status || null,
    assignee: filters.assignee?.[0] || null,
    search: filters.search || null,
    startDate: filters.dateRange?.start || null,
    endDate: filters.dateRange?.end || null,
    page: currentPage,
    size: pageSize,
  });

  // Fetch selected task details from API (only when a task is selected)
  const {
    data: taskDetail,
    isLoading: isLoadingDetail,
    error: detailError,
  } = useTaskDetail(selectedTaskId);

  // Task update mutation (for assignment in preview mode)
  const updateTaskMutation = useUpdateTask(selectedTaskId, {
    onError: (error) => {
      console.error("Failed to update task:", error);
    },
  });

  // Calculate pagination metadata
  const totalPages = tasksData?.pages || 1;

  // Handle page changes
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return;
    setCurrentPage(newPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Assignment handler functions (for preview mode)
  const handleAssignToMe = () => {
    if (!selectedTaskId || !currentUser) return;
    
    // If task is currently "TODO", change status to "IN_PROGRESS" when assigning
    const updates: { assignee: string; status?: TaskStatus } = { assignee: currentUser };
    if (taskDetail?.status === 'TODO') {
      updates.status = 'IN_PROGRESS';
    }
    
    updateTaskMutation.mutate(updates);
  };

  const handleAssignToUser = (username: string) => {
    if (!selectedTaskId) return;
    
    // If task is currently "TODO", change status to "IN_PROGRESS" when assigning
    const updates: { assignee: string; status?: TaskStatus } = { assignee: username };
    if (taskDetail?.status === 'TODO') {
      updates.status = 'IN_PROGRESS';
    }
    
    updateTaskMutation.mutate(updates);
  };

  const handleUnassign = () => {
    if (!selectedTaskId) return;
    updateTaskMutation.mutate({ assignee: null });
  };

  // Task selection handler
  const handleTaskSelect = (taskId: number, taskHumanId: string) => {
    setSelectedTaskId(taskId);
    
    if (breakpoint === 'mobile') {
      // On mobile, navigate to detail view
      navigate(`/tasks/${taskHumanId}`);
    } else {
      // On non-mobile, stay in list view and show read-only timeline
      // (visibleColumns will be updated by useEffect)
    }
  };

  // Double-click handler - always navigate to detail view
  const handleTaskDoubleClick = (taskId: number, taskHumanId: string) => {
    navigate(`/tasks/${taskHumanId}`);
  };

  // Handle "Open Task" from timeline to navigate to detail view
  const handleOpenTask = () => {
    if (taskDetail?.human_id) {
      navigate(`/tasks/${taskDetail.human_id}`);
    }
  };

  // Handle back to list (for mobile only)
  const handleBackToList = () => {
    setSelectedTaskId(null);
    setVisibleColumns('left');
  };

  return (
    <DefaultPageLayout priority={taskDetail?.priority || undefined}>
      <ThreeColumnLayout
        leftColumn={
          <EntityList
            items={tasksData?.items ?? []}
            selectedId={selectedTaskId}
            onSelect={handleTaskSelect}
            onDoubleClick={handleTaskDoubleClick}
            getItemHref={(_id, humanId) => `/tasks/${humanId}`}
            filters={filters}
            onFilterChange={setFilters}
            statusOptions={[
              { value: 'TODO', label: 'To Do' },
              { value: 'IN_PROGRESS', label: 'In Progress' },
              { value: 'DONE', label: 'Done' },
            ]}
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={tasksData?.total}
            onPageChange={handlePageChange}
            isLoading={isLoading}
            error={error}
            users={users}
            usersLoading={isLoadingUsers}
            getItemIds={(taskItem: TaskRead) => ({ id: taskItem.id, humanId: taskItem.human_id })}
            mapItemToCard={(taskItem: TaskRead) => ({
              id: taskItem.human_id,
              title: taskItem.title,
              description: taskItem.description || '',
              timestamp: taskItem.created_at,
              assignee: taskItem.assignee || 'Unassigned',
              tags: taskItem.tags || [],
              state: taskStateToMenuCardState(taskStatusToUIState(taskItem.status)),
              priority: priorityToUIPriority(taskItem.priority),
            })}
            emptyMessage="No tasks found"
          />
        }
        centerColumn={
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
            mode="readonly"
            onAssignToMe={handleAssignToMe}
            onAssignToUser={handleAssignToUser}
            onUnassign={handleUnassign}
            onBackToList={handleBackToList}
            onOpenEntity={handleOpenTask}
          />
        }
        rightColumn={<div></div>}
        visibleColumns={visibleColumns}
        onVisibleColumnsChange={setVisibleColumns}
        columnConfig={getColumnConfig(selectedTaskId)}
        dimLeftColumn={!!selectedTaskId}
      />
    </DefaultPageLayout>
  );
}

export default TasksListPage;
