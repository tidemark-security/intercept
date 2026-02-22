import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { RejectRecommendationRequest } from '@/types/generated/models/RejectRecommendationRequest';
import type { TriageRecommendationRead } from '@/types/generated/models/TriageRecommendationRead';
import { queryKeys } from './queryKeys';

interface UseRejectTriageRecommendationOptions {
  onSuccess?: (data: TriageRecommendationRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to reject a triage recommendation using TanStack Query mutation
 * 
 * @param alertId - The ID of the alert with the recommendation
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useRejectTriageRecommendation(
  alertId: number | null,
  options?: UseRejectTriageRecommendationOptions
): UseMutationResult<TriageRecommendationRead, Error, RejectRecommendationRequest> {
  const queryClient = useQueryClient();

  return useMutation<TriageRecommendationRead, Error, RejectRecommendationRequest>({
    mutationFn: async (rejectRequest: RejectRecommendationRequest) => {
      if (alertId === null) {
        throw new Error('Alert ID is required');
      }
      return AlertsService.rejectTriageRecommendationApiV1AlertsAlertIdTriageRecommendationRejectPost({
        alertId,
        requestBody: rejectRequest,
      });
    },

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
