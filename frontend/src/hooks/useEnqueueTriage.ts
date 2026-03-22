import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { TriageRecommendationRead } from '@/types/generated/models/TriageRecommendationRead';
import { queryKeys } from './queryKeys';

interface UseEnqueueTriageOptions {
  onSuccess?: (data: TriageRecommendationRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to enqueue AI triage for an alert.
 * 
 * Creates a QUEUED placeholder recommendation and submits the triage job to the worker queue.
 * If a QUEUED or FAILED recommendation already exists, it will be updated in-place (retry).
 * 
 * @param alertId - The ID of the alert to triage
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useEnqueueTriage(
  alertId: number | string | null,
  options?: UseEnqueueTriageOptions
): UseMutationResult<TriageRecommendationRead, Error, void> {
  const queryClient = useQueryClient();
  
  // Parse alertId if it's a human ID string like "ALT-0000123"
  const numericAlertId = typeof alertId === 'string' 
    ? parseInt(alertId.replace('ALT-', ''), 10)
    : alertId;

  return useMutation<TriageRecommendationRead, Error, void>({
    mutationFn: async () => {
      if (numericAlertId === null || isNaN(numericAlertId)) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.enqueueTriageRecommendationApiV1AlertsAlertIdTriageRecommendationEnqueuePost({
        alertId: numericAlertId,
      });
    },

    onSuccess: (data) => {
      // Invalidate the alerts list to refetch with updated triage status
      queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });
      
      // Invalidate the specific alert detail to refetch with new triage recommendation
      if (numericAlertId !== null) {
        queryClient.invalidateQueries({ 
          queryKey: queryKeys.alert.detailBase(numericAlertId), 
          exact: false 
        });
      }

      options?.onSuccess?.(data);
    },
    
    onError: (error) => {
      options?.onError?.(error);
    },
  });
}
