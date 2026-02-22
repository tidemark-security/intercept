import { useCallback } from 'react';
import { useUpdateCase } from '@/hooks/useUpdateCase';
import { useUpdateTask } from '@/hooks/useUpdateTask';
import { uiStateToCaseStatus, uiStateToTaskStatus } from '@/utils/statusHelpers';
import type { UIState } from '@/utils/statusHelpers';

type EntityType = 'case' | 'task';

interface UseStatusHandlersOptions {
  /** Type of entity */
  entityType: EntityType;
  /** ID of the entity */
  entityId: number | null;
}

interface StatusHandlers {
  /** Handle status change (close with specific status) */
  handleCloseEntity: (status: UIState) => void;
  /** Reopen entity (set status to IN_PROGRESS) */
  handleReopenEntity: () => void;
  /** Whether an update is currently pending */
  isPending: boolean;
}

/**
 * Hook to provide unified status handlers for cases and tasks.
 * 
 * Handles the conversion from UI status (lowercase) to API status (UPPERCASE)
 * for the appropriate entity type.
 * 
 * @param options - Configuration options
 * @returns Status handler functions and pending state
 * 
 * @example
 * ```tsx
 * const { handleCloseEntity, handleReopenEntity, isPending } = useStatusHandlers({
 *   entityType: 'case',
 *   entityId: selectedCaseId,
 * });
 * ```
 */
export function useStatusHandlers(options: UseStatusHandlersOptions): StatusHandlers {
  const { entityType, entityId } = options;

  // Initialize mutations for both entity types
  // Only one will be used based on entityType
  const updateCaseMutation = useUpdateCase(
    entityType === 'case' ? entityId : null,
    {
      onError: (error) => {
        console.error(`Failed to update case status:`, error);
      },
    }
  );

  const updateTaskMutation = useUpdateTask(
    entityType === 'task' ? entityId : null,
    {
      onError: (error) => {
        console.error(`Failed to update task status:`, error);
      },
    }
  );

  const handleCloseEntity = useCallback((status: UIState) => {
    if (!entityId) return;

    if (entityType === 'case') {
      const apiStatus = uiStateToCaseStatus(status);
      updateCaseMutation.mutate({ status: apiStatus });
    } else {
      const apiStatus = uiStateToTaskStatus(status);
      updateTaskMutation.mutate({ status: apiStatus });
    }
  }, [entityId, entityType, updateCaseMutation, updateTaskMutation]);

  const handleReopenEntity = useCallback(() => {
    if (!entityId) return;
    if (entityType === 'case') {
      updateCaseMutation.mutate({ status: 'IN_PROGRESS' });
    } else {
      updateTaskMutation.mutate({ status: 'IN_PROGRESS' });
    }
  }, [entityId, entityType, updateCaseMutation, updateTaskMutation]);

  return {
    handleCloseEntity,
    handleReopenEntity,
    isPending: entityType === 'case' ? updateCaseMutation.isPending : updateTaskMutation.isPending,
  };
}
