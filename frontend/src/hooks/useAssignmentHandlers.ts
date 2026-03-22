import { useCallback } from 'react';
import { useSession } from '@/contexts/sessionContext';
import { useUpdateCase } from '@/hooks/useUpdateCase';
import { useUpdateTask } from '@/hooks/useUpdateTask';
import type { TaskStatus } from '@/types/generated/models/TaskStatus';

type EntityType = 'case' | 'task';

interface UseAssignmentHandlersOptions {
  /** Type of entity being assigned */
  entityType: EntityType;
  /** ID of the entity */
  entityId: number | null;
  /** Current status of the entity (required for task auto-transition) */
  currentStatus?: string;
  /** Current assignee of the entity (required for checkAndAssignToMe) */
  currentAssignee?: string | null;
}

interface AssignmentHandlers {
  /** Assign the entity to the current user */
  handleAssignToMe: () => void;
  /** Assign the entity to a specific user */
  handleAssignToUser: (username: string) => void;
  /** Unassign the entity */
  handleUnassign: () => void;
  /** Auto-assign to current user if currently unassigned (task-specific) */
  checkAndAssignToMe: () => void;
  /** Whether an update is currently pending */
  isPending: boolean;
}

/**
 * Hook to provide unified assignment handlers for cases and tasks.
 * 
 * For tasks, automatically transitions status from TODO → IN_PROGRESS when assigned.
 * 
 * @param options - Configuration options
 * @returns Assignment handler functions and pending state
 * 
 * @example
 * ```tsx
 * const { handleAssignToMe, handleAssignToUser, handleUnassign, isPending } = useAssignmentHandlers({
 *   entityType: 'task',
 *   entityId: selectedTaskId,
 *   currentStatus: taskDetail?.status,
 *   currentAssignee: taskDetail?.assignee,
 * });
 * ```
 */
export function useAssignmentHandlers(options: UseAssignmentHandlersOptions): AssignmentHandlers {
  const { entityType, entityId, currentStatus, currentAssignee } = options;
  const { user } = useSession();
  const currentUser = user?.username || null;

  // Initialize mutations for both entity types
  // Only one will be used based on entityType
  const updateCaseMutation = useUpdateCase(
    entityType === 'case' ? entityId : null,
    {
      onError: (error) => {
        console.error(`Failed to update case assignment:`, error);
      },
    }
  );

  const updateTaskMutation = useUpdateTask(
    entityType === 'task' ? entityId : null,
    {
      onError: (error) => {
        console.error(`Failed to update task assignment:`, error);
      },
    }
  );

  const handleAssignToMe = useCallback(() => {
    if (!entityId || !currentUser) return;

    if (entityType === 'task') {
      // Task-specific: auto-transition TODO → IN_PROGRESS when assigned
      const updates: { assignee: string; status?: TaskStatus } = { assignee: currentUser };
      if (currentStatus === 'TODO') {
        updates.status = 'IN_PROGRESS';
      }
      updateTaskMutation.mutate(updates);
    } else {
      updateCaseMutation.mutate({ assignee: currentUser });
    }
  }, [entityId, entityType, currentUser, currentStatus, updateCaseMutation, updateTaskMutation]);

  const handleAssignToUser = useCallback((username: string) => {
    if (!entityId) return;

    if (entityType === 'task') {
      // Task-specific: auto-transition TODO → IN_PROGRESS when assigned
      const updates: { assignee: string; status?: TaskStatus } = { assignee: username };
      if (currentStatus === 'TODO') {
        updates.status = 'IN_PROGRESS';
      }
      updateTaskMutation.mutate(updates);
    } else {
      updateCaseMutation.mutate({ assignee: username });
    }
  }, [entityId, entityType, currentStatus, updateCaseMutation, updateTaskMutation]);

  const handleUnassign = useCallback(() => {
    if (!entityId) return;
    if (entityType === 'case') {
      updateCaseMutation.mutate({ assignee: null });
    } else {
      updateTaskMutation.mutate({ assignee: null });
    }
  }, [entityId, entityType, updateCaseMutation, updateTaskMutation]);

  // Task-specific: auto-assign to current user if unassigned
  const checkAndAssignToMe = useCallback(() => {
    if (entityType !== 'task' || !entityId || !currentUser || currentAssignee) return;

    const updates: { assignee: string; status?: TaskStatus } = { assignee: currentUser };
    if (currentStatus === 'TODO') {
      updates.status = 'IN_PROGRESS';
    }
    updateTaskMutation.mutate(updates);
  }, [entityType, entityId, currentUser, currentAssignee, currentStatus, updateTaskMutation]);

  return {
    handleAssignToMe,
    handleAssignToUser,
    handleUnassign,
    checkAndAssignToMe,
    isPending: entityType === 'case' ? updateCaseMutation.isPending : updateTaskMutation.isPending,
  };
}
