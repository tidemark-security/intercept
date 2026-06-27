import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { OpenAPI } from '@/types/generated/core/OpenAPI';
import { request as __request } from '@/types/generated/core/request';
import type { AlertBulkActionResponse } from '@/types/generated/models/AlertBulkActionResponse';
import type { ClosedAlertStatus } from '@/utils/statusLabels';
import { queryKeys } from './queryKeys';

export interface LinkedAlertResolutionUpdate {
  alert_id: number;
  status: ClosedAlertStatus;
}

export interface ResolveLinkedAlertsRequest {
  alert_updates: LinkedAlertResolutionUpdate[];
  note?: string;
}

interface UseResolveLinkedAlertsOptions {
  onSuccess?: (data: AlertBulkActionResponse) => void;
  onError?: (error: Error) => void;
}

function resolveLinkedAlerts(
  caseId: number,
  requestBody: ResolveLinkedAlertsRequest,
) {
  return __request<AlertBulkActionResponse>(OpenAPI, {
    method: 'POST',
    url: '/api/v1/cases/{case_id}/resolve-linked-alerts',
    path: {
      'case_id': caseId,
    },
    body: requestBody,
    mediaType: 'application/json',
    errors: {
      400: 'Bad Request',
      422: 'Validation Error',
    },
  });
}

export function useResolveLinkedAlerts(
  caseId: number | null,
  options?: UseResolveLinkedAlertsOptions,
): UseMutationResult<AlertBulkActionResponse, Error, ResolveLinkedAlertsRequest> {
  const queryClient = useQueryClient();

  return useMutation<AlertBulkActionResponse, Error, ResolveLinkedAlertsRequest>({
    mutationFn: (requestBody) => {
      if (caseId === null) {
        throw new Error('Case ID is required');
      }
      return resolveLinkedAlerts(caseId, requestBody);
    },
    onSuccess: async (data) => {
      if (caseId !== null) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.case.detailBase(caseId),
          exact: false,
        });
      }
      await queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.alert.listBase() });

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
