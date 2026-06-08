import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { AlertsService } from '@/types/generated/services/AlertsService';
import type { AlertBulkActionRequest } from '@/types/generated/models/AlertBulkActionRequest';
import type { AlertBulkActionResponse } from '@/types/generated/models/AlertBulkActionResponse';
import { queryKeys } from './queryKeys';

interface UseBulkAlertActionOptions {
  onSuccess?: (data: AlertBulkActionResponse) => void;
  onError?: (error: Error) => void;
}

export function useBulkAlertAction(
  options?: UseBulkAlertActionOptions
): UseMutationResult<AlertBulkActionResponse, Error, AlertBulkActionRequest> {
  const queryClient = useQueryClient();

  return useMutation<AlertBulkActionResponse, Error, AlertBulkActionRequest>({
    mutationFn: (requestBody) =>
      AlertsService.bulkAlertActionApiV1AlertsBulkActionsPost({ requestBody }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });
      queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() });
      data.updated_alerts.forEach((alert) => {
        queryClient.invalidateQueries({
          queryKey: queryKeys.alert.detailBase(alert.id),
          exact: false,
        });
      });
      options?.onSuccess?.(data);
    },
    onError: (error) => {
      options?.onError?.(error);
    },
  });
}
