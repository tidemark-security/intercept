import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AcceptRecommendationRequest } from '@/types/generated/models/AcceptRecommendationRequest';
import type { AcceptRecommendationResponse } from '@/types/generated/models/AcceptRecommendationResponse';
import { queryKeys } from './queryKeys';

interface UseAcceptTriageRecommendationOptions {
  onSuccess?: (data: AcceptRecommendationResponse) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to accept a triage recommendation using TanStack Query mutation
 * 
 * When a recommendation is accepted:
 * - Selected patches (status, priority, assignee, tags) are applied to the alert
 * - If request_escalate_to_case is true, a case is created and tasks are spawned
 * 
 * @param alertId - The ID of the alert with the recommendation
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useAcceptTriageRecommendation(
  alertId: number | null,
  options?: UseAcceptTriageRecommendationOptions
): UseMutationResult<AcceptRecommendationResponse, Error, AcceptRecommendationRequest> {
  const queryClient = useQueryClient();

  return useMutation<AcceptRecommendationResponse, Error, AcceptRecommendationRequest>({
    mutationFn: async (acceptRequest: AcceptRecommendationRequest) => {
      if (alertId === null) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.acceptTriageRecommendationApiV1AlertsAlertIdTriageRecommendationAcceptPost({
        alertId,
        requestBody: acceptRequest,
      });
    },

    onSuccess: (data) => {
      // Invalidate the alerts list to refetch with updated data
      queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });
      
      // Invalidate the specific alert detail to refetch
      if (alertId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.alert.detailBase(alertId), exact: false });
      }

      // If a case was created, invalidate cases list too
      if (data.case_id) {
        queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() });
        queryClient.invalidateQueries({ queryKey: queryKeys.task.listBase() });
      }

      options?.onSuccess?.(data);
    },
    
    onError: (error) => {
      options?.onError?.(error);
    }
  });
}
