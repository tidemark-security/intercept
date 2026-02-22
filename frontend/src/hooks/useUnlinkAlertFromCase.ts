import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import { queryKeys } from './queryKeys';

interface UseUnlinkAlertFromCaseOptions {
  onSuccess?: (data: AlertRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to unlink an alert from its associated case using TanStack Query mutation
 * 
 * This will:
 * - Remove the case_id from the alert
 * - Clear the linked_at timestamp
 * - Change the status from ESCALATED back to IN_PROGRESS
 * 
 * @param alertId - The ID of the alert to unlink
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useUnlinkAlertFromCase(
  alertId: number | null,
  options?: UseUnlinkAlertFromCaseOptions
): UseMutationResult<AlertRead, Error, void> {
  const queryClient = useQueryClient();

  return useMutation<AlertRead, Error, void>({
    mutationFn: async () => {
      if (alertId === null) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.unlinkAlertFromCaseApiV1AlertsAlertIdUnlinkCasePost({
        alertId,
      });
    },

    onSuccess: (data) => {
      // Invalidate the alerts list to refetch with updated data
      queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });
      
      // Invalidate the specific alert detail to refetch
      if (alertId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.alert.detailBase(alertId), exact: false });
      }

      // Invalidate cases list in case alert counts have changed
      queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() });

      options?.onSuccess?.(data);
    },
    
    onError: (error) => {
      options?.onError?.(error);
    }
  });
}
