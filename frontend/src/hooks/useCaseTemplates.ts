import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type {
  CaseTemplatePayload,
  CaseTemplateStatus,
  TemplateTaskOverride,
} from '@/types/caseTemplates';
import {
  applyCaseTemplate,
  createCaseTemplate,
  deleteCaseTemplate,
  disableCaseTemplate,
  listCaseTemplates,
  publishCaseTemplate,
  updateCaseTemplate,
} from '@/services/caseTemplatesApi';
import { queryKeys } from '@/hooks/queryKeys';

export const caseTemplateKeys = {
  all: ['case-templates'] as const,
  list: (statuses?: CaseTemplateStatus[], search?: string | null) =>
    ['case-templates', { statuses, search }] as const,
};

export function useCaseTemplates(statuses?: CaseTemplateStatus[], search?: string | null) {
  return useQuery({
    queryKey: caseTemplateKeys.list(statuses, search),
    queryFn: () => listCaseTemplates(statuses, search),
    staleTime: 60_000,
  });
}

export function useCreateCaseTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CaseTemplatePayload) => createCaseTemplate(payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseTemplateKeys.all }),
  });
}

export function useUpdateCaseTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: CaseTemplatePayload }) => updateCaseTemplate(id, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseTemplateKeys.all }),
  });
}

export function usePublishCaseTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => publishCaseTemplate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseTemplateKeys.all }),
  });
}

export function useDisableCaseTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => disableCaseTemplate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseTemplateKeys.all }),
  });
}

export function useDeleteCaseTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteCaseTemplate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseTemplateKeys.all }),
  });
}

export function useApplyCaseTemplate(caseId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ templateId, taskOverrides }: { templateId: number; taskOverrides: TemplateTaskOverride[] }) => {
      if (caseId === null) {
        throw new Error('Case ID is required');
      }
      return applyCaseTemplate(caseId, templateId, taskOverrides);
    },
    onSuccess: () => {
      if (caseId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.case.detailBase(caseId), exact: false });
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.task.listBase() });
    },
  });
}
