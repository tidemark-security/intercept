import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AlertTriageRequest } from '@/types/generated/models/AlertTriageRequest';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import { queryKeys } from './queryKeys';

interface UseTriageAlertOptions {
  onSuccess?: (data: AlertRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to triage an alert using TanStack Query mutation
 * 
 * @param alertId - The ID of the alert to triage
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useTriageAlert(
  alertId: number | null,
  options?: UseTriageAlertOptions
): UseMutationResult<AlertRead, Error, AlertTriageRequest> {
  const queryClient = useQueryClient();

  return useMutation<AlertRead, Error, AlertTriageRequest>({
    mutationFn: async (triageRequest: AlertTriageRequest) => {
      if (alertId === null) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.triageAlertApiV1AlertsAlertIdTriagePost({
        alertId,
        requestBody: triageRequest,
      });
    },

    // On success, invalidate and refetch queries to ensure consistency
    onSuccess: (data) => {
      // Invalidate the alerts list to refetch with updated data
      queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });
      
      // Invalidate the specific alert detail to refetch
      if (alertId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.alert.detailBase(alertId), exact: false });
      }

      options?.onSuccess?.(data);
    },
    
    onError: (error) => {
      options?.onError?.(error);
    }
  });
}
