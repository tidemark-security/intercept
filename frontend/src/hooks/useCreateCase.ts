import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { CasesService } from '@/types/generated/services/CasesService';
import type { CaseCreate } from '@/types/generated/models/CaseCreate';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import { queryKeys } from './queryKeys';

interface UseCreateCaseOptions {
  onSuccess?: (data: CaseRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to create a new case using TanStack Query mutation
 *
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useCreateCase(
  options?: UseCreateCaseOptions
): UseMutationResult<CaseRead, Error, CaseCreate, unknown> {
  const queryClient = useQueryClient();

  return useMutation<CaseRead, Error, CaseCreate, unknown>({
    mutationFn: async (caseCreate: CaseCreate) => {
      return CasesService.createCaseApiV1CasesPost({
        requestBody: caseCreate,
      });
    },

    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() });
      options?.onSuccess?.(data);
    },

    onError: (error) => {
      options?.onError?.(error);
    },
  });
}
