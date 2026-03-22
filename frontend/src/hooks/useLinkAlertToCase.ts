import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import { queryKeys } from './queryKeys';

interface UseLinkAlertToCaseOptions {
  onSuccess?: (data: AlertRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to link an alert to an existing case using TanStack Query mutation
 * 
 * @param alertId - The ID of the alert to link
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useLinkAlertToCase(
  alertId: number | null,
  options?: UseLinkAlertToCaseOptions
): UseMutationResult<AlertRead, Error, number> {
  const queryClient = useQueryClient();

  return useMutation<AlertRead, Error, number>({
    mutationFn: async (caseId: number) => {
      if (alertId === null) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.linkAlertToCaseApiV1AlertsAlertIdLinkCaseCaseIdPost({
        alertId,
        caseId,
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
