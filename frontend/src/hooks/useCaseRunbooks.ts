import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  CaseRunbookPayload,
  CaseRunbookStatus,
  RunbookTaskOverride,
} from '@/types/caseRunbooks';
import {
  applyCaseRunbook,
  createCaseRunbook,
  deleteCaseRunbook,
  disableCaseRunbook,
  listCaseRunbooks,
  publishCaseRunbook,
  updateCaseRunbook,
} from '@/services/caseRunbooksApi';
import { queryKeys } from '@/hooks/queryKeys';

export const caseRunbookKeys = {
  all: ['case-runbooks'] as const,
  list: (statuses?: CaseRunbookStatus[], search?: string | null) =>
    ['case-runbooks', { statuses, search }] as const,
};

export function useCaseRunbooks(statuses?: CaseRunbookStatus[], search?: string | null) {
  return useQuery({
    queryKey: caseRunbookKeys.list(statuses, search),
    queryFn: () => listCaseRunbooks(statuses, search),
    staleTime: 60_000,
  });
}

export function useCreateCaseRunbook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CaseRunbookPayload) => createCaseRunbook(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseRunbookKeys.all }),
  });
}

export function useUpdateCaseRunbook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: CaseRunbookPayload }) => updateCaseRunbook(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseRunbookKeys.all }),
  });
}

export function usePublishCaseRunbook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => publishCaseRunbook(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseRunbookKeys.all }),
  });
}

export function useDisableCaseRunbook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => disableCaseRunbook(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseRunbookKeys.all }),
  });
}

export function useDeleteCaseRunbook() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCaseRunbook(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseRunbookKeys.all }),
  });
}

export function useApplyCaseRunbook(caseId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ runbookId, taskOverrides }: { runbookId: number; taskOverrides: RunbookTaskOverride[] }) => {
      if (caseId === null) {
        throw new Error('Case ID is required');
      }
      return applyCaseRunbook(caseId, runbookId, taskOverrides);
    },
    onSuccess: () => {
      if (caseId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.case.detailBase(caseId), exact: false });
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.task.listBase() });
    },
  });
}
