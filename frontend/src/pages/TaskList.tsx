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
import { UnifiedTimeline } from "@/components/timeline/UnifiedTimeline";
import { useTasks } from "@/hooks/useTasks";
import { useTaskDetail } from "@/hooks/useTaskDetail";
import { useUsers } from "@/hooks/useUsers";
import { useUpdateTask } from "@/hooks/useUpdateTask";
import { useSession } from "@/contexts/sessionContext";
import { useBreakpoint } from "@/hooks/useBreakpoint";
import { canShowSplitPaneCenter, useViewportWidth } from "@/hooks/useSplitPaneCenter";
import { useURLFilters } from "@/hooks/useURLFilters";
import { toEntityListQueryFilters } from "@/utils/entityListQueryFilters";
import { normalizeQueueSearch } from "@/utils/queueSearch";
import { useQueueSearch, type QueueListRow } from "@/hooks/useQueueSearch";
import { useTagFilterClick } from "@/hooks/useTagFilterClick";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";
import type { TaskFilterState } from "@/types/filters";
import { taskStatusToUIState, priorityToUIPriority, taskStateToMenuCardState } from "@/utils/statusHelpers";
import { TASK_STATUS_OPTIONS } from "@/utils/statusLabels";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";

const TASK_SORT_OPTIONS = [
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
 * Tasks List Page - Browse and filter tasks with optional preview
 * 
 * Features:
 * - Paginated task list with filters
 * - Read-only timeline preview in center column (when task selected)
 * - On mobile: tapping a task navigates to detail page
 * - On non-mobile: preview beside or floating over the task list
 * 
 * @returns The Tasks List page component
 */
function TasksListPage() {
  useDocumentTitle("Tasks");
  const navigate = useViewTransitionNavigate();
  const location = useLocation();
  const { user, isAuditor } = useSession();
  const currentUser = user?.username || null;

  // UI state for filtering - synced with URL query params
  const { filters, setFilters, setSearch, currentPage, setCurrentPage } = useURLFilters<TaskFilterState>({
    queue: "tasks",
    userId: user?.id,
    defaults: {
      search: "",
      assignee: null,
      status: ["TODO" as TaskStatus, "IN_PROGRESS" as TaskStatus],
      includeTags: null,
      excludeTags: null,
      dateRange: null,
      sortBy: "created_at",
      sortOrder: "desc",
    },
  });
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const handleFilterByTag = useTagFilterClick(filters, setFilters);

  const [taskListWidth, setTaskListWidth] = useState<number>(() => getPersistedWidth(768));

  // Reactive breakpoint state
  const breakpoint = useBreakpoint();
  const viewportWidth = useViewportWidth();
  const showSplitCenter = canShowSplitPaneCenter(viewportWidth, taskListWidth, breakpoint);

  // Fetch users for assignee dropdown
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});

  // Fetch tasks list from API
  const pageSize = 50;
  const searchQuery = normalizeQueueSearch(filters.search);
  const queue = useTasks({
    ...toEntityListQueryFilters(filters),
    search: null,
    enabled: !searchQuery,
    page: currentPage,
    size: pageSize,
  });
  const searchedQueue = useQueueSearch("task", filters, currentPage, pageSize);
  const { data: tasksData, isLoading, error } = searchQuery ? searchedQueue : queue;
  const bulk = useEntityBulkActions("task", tasksData?.items, {
    enabled: !isAuditor, users, currentUser, usersLoading: isLoadingUsers, showSplitCenter, selectionScope: searchQuery,
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
    bulk.clear();
    if (breakpoint === 'mobile') {
      navigate(`/tasks/${taskHumanId}${location.search}`);
    } else {
      setSelectedTaskId(taskId);
    }
  };

  // Double-click handler - always navigate to detail view
  const handleTaskDoubleClick = (taskId: number, taskHumanId: string) => {
    navigate(`/tasks/${taskHumanId}${location.search}`);
  };

  // Handle "Open Task" from timeline to navigate to detail view
  const handleOpenTask = () => {
    if (taskDetail?.human_id) {
      navigate(`/tasks/${taskDetail.human_id}${location.search}`);
    }
  };

  // Handle back to list (for mobile only)
  const handleBackToList = () => {
    setSelectedTaskId(null);
  };

  return (
    <DefaultPageLayout priority={bulk.hasMultiple ? undefined : taskDetail?.priority || undefined}>
      <EntityQueueLayout
        searchQuery={searchQuery}
        entityType="task"
        isMobile={breakpoint === 'mobile'}
        showSplitCenter={showSplitCenter}
        selectedId={selectedTaskId}
        listWidth={taskListWidth}
        onListWidthChange={setTaskListWidth}
        onSelect={handleTaskSelect}
        selection={bulk.selectionColumns ? {
          columns: bulk.selectionColumns,
          toolbar: bulk.toolbarProps,
          summary: bulk.summaryProps,
        } : undefined}
        renderList={(queueListProps) => (
          <EntityList
            items={tasksData?.items ?? []}
            selectedId={bulk.hasMultiple ? null : selectedTaskId}
            {...bulk.listProps}
            {...queueListProps}
            onDoubleClick={handleTaskDoubleClick}
            getItemHref={(_id, humanId) => `/tasks/${humanId}${location.search}`}
            filters={filters}
            onFilterChange={setFilters}
            onSearchChange={setSearch}
            savedFilterQueue="tasks"
            retrySearch={searchQuery ? searchedQueue.refetch : undefined}
            enableTagFilters
            onTagClick={handleFilterByTag}
            statusOptions={TASK_STATUS_OPTIONS}
            sortOptions={TASK_SORT_OPTIONS}
            currentPage={currentPage}
            totalPages={totalPages}
            totalItems={tasksData?.total}
            onPageChange={handlePageChange}
            alwaysShowPaginator
            isLoading={isLoading}
            error={error}
            users={users}
            usersLoading={isLoadingUsers}
            getItemIds={(taskItem: QueueListRow) => ({ id: taskItem.id, humanId: taskItem.human_id })}
            mapItemToCard={(taskItem: QueueListRow) => ({
              id: taskItem.human_id,
              title: taskItem.title,
              description: taskItem.description || '',
              timestamp: taskItem.created_at,
              assignee: taskItem.assignee || 'Unassigned',
              tags: taskItem.tags || [],
              state: taskStateToMenuCardState(taskStatusToUIState(taskItem.status as TaskStatus)),
              priority: priorityToUIPriority(taskItem.priority),
            })}
            emptyMessage="No tasks found"
          />
        )}
        detail={
          <UnifiedTimeline
            searchQuery={searchQuery}
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
      />
      {bulk.dialogProps && <BulkActionModal {...bulk.dialogProps} />}
    </DefaultPageLayout>
  );
}

export default TasksListPage;
