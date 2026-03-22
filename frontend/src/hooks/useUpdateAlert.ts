import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AlertUpdate } from '@/types/generated/models/AlertUpdate';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import { queryKeys } from './queryKeys';

interface UseUpdateAlertOptions {
  onSuccess?: (data: AlertRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to update an alert using TanStack Query mutation
 * Provides optimistic updates, automatic query invalidation, and error handling
 * 
 * @param alertId - The ID of the alert to update
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useUpdateAlert(
  alertId: number | null,
  options?: UseUpdateAlertOptions
): UseMutationResult<AlertRead, Error, AlertUpdate, { previousAlert: AlertRead | undefined }> {
  const queryClient = useQueryClient();

  return useMutation<AlertRead, Error, AlertUpdate, { previousAlert: AlertRead | undefined }>({
    mutationFn: async (alertUpdate: AlertUpdate) => {
      if (alertId === null) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.updateAlertApiV1AlertsAlertIdPut({
        alertId,
        requestBody: alertUpdate,
      });
    },
    
    // Optimistic update: immediately update the cache before the mutation completes
    onMutate: async (newAlert: AlertUpdate) => {
      if (alertId === null) return { previousAlert: undefined };

      // Cancel any outgoing refetches to prevent overwriting optimistic update
      // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
      await queryClient.cancelQueries({ queryKey: queryKeys.alert.detailBase(alertId), exact: false });

      // Snapshot the previous value for rollback
      // Use partial key matching to handle query keys with options
      const queriesData = queryClient.getQueriesData<AlertRead>({ queryKey: queryKeys.alert.detailBase(alertId), exact: false });
      const previousAlert = queriesData.length > 0 ? queriesData[0][1] : undefined;

      // Optimistically update the cache
      if (previousAlert) {
        // Create a properly typed updated alert by merging non-null values
        const updatedAlert: AlertRead = {
          ...previousAlert,
          ...(newAlert.title !== null && newAlert.title !== undefined ? { title: newAlert.title } : {}),
          ...(newAlert.description !== undefined ? { description: newAlert.description } : {}),
          ...(newAlert.status !== null && newAlert.status !== undefined ? { status: newAlert.status } : {}),
          ...(newAlert.priority !== undefined ? { priority: newAlert.priority } : {}),
          ...(newAlert.source !== undefined ? { source: newAlert.source } : {}),
          ...(newAlert.assignee !== undefined ? { assignee: newAlert.assignee } : {}),
          ...(newAlert.tags !== undefined ? { tags: newAlert.tags } : {}),
        };
        
        queryClient.setQueriesData<AlertRead>({ queryKey: queryKeys.alert.detailBase(alertId), exact: false }, updatedAlert);
      }

      // Return context with the previous value for rollback
      return { previousAlert };
    },

    // On error, roll back the optimistic update
    onError: (error, _newAlert, context) => {
      if (context?.previousAlert && alertId !== null) {
        queryClient.setQueriesData({ queryKey: queryKeys.alert.detailBase(alertId), exact: false }, context.previousAlert);
      }
      options?.onError?.(error);
    },

    // On success, invalidate and refetch queries to ensure consistency
    onSuccess: (data) => {
      // Invalidate the alerts list to refetch with updated data
      queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });
      
      // Invalidate the specific alert detail to refetch
      // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
      if (alertId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.alert.detailBase(alertId), exact: false });
      }

      options?.onSuccess?.(data);
    },
  });
}
