import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { CasesService } from '@/types/generated/services/CasesService';
import type { CaseUpdate } from '@/types/generated/models/CaseUpdate';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import { queryKeys } from './queryKeys';

interface UseUpdateCaseOptions {
  onSuccess?: (data: CaseRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to update a case using TanStack Query mutation
 * Provides optimistic updates, automatic query invalidation, and error handling
 * 
 * @param caseId - The ID of the case to update
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useUpdateCase(
  caseId: number | null,
  options?: UseUpdateCaseOptions
): UseMutationResult<CaseRead, Error, CaseUpdate, { previousCases: Array<[readonly unknown[], CaseRead | undefined]> }> {
  const queryClient = useQueryClient();

  return useMutation<CaseRead, Error, CaseUpdate, { previousCases: Array<[readonly unknown[], CaseRead | undefined]> }>({
    mutationFn: async (caseUpdate: CaseUpdate) => {
      if (caseId === null) {
        throw new Error('Case ID is required');
      }
      return CasesService.updateCaseApiV1CasesCaseIdPut({
        caseId,
        requestBody: caseUpdate,
      });
    },
    
    // Optimistic update: immediately update the cache before the mutation completes
    onMutate: async (newCase: CaseUpdate) => {
      if (caseId === null) return { previousCases: [] };

      // Cancel any outgoing refetches to prevent overwriting optimistic update
      // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
      await queryClient.cancelQueries({ queryKey: queryKeys.case.detailBase(caseId), exact: false });

      // Snapshot all matching query variants for rollback (handles keys with different options)
      const queriesData = queryClient.getQueriesData<CaseRead>({ queryKey: queryKeys.case.detailBase(caseId), exact: false });
      const previousCases = queriesData.map(([queryKey, data]) => [queryKey as readonly unknown[], data]);

      const optimisticPatch = {
        ...(newCase.title !== null && newCase.title !== undefined ? { title: newCase.title } : {}),
        ...(newCase.description !== undefined ? { description: newCase.description } : {}),
        ...(newCase.status !== null && newCase.status !== undefined ? { status: newCase.status } : {}),
        ...(newCase.priority !== undefined ? { priority: newCase.priority } : {}),
        ...(newCase.assignee !== undefined ? { assignee: newCase.assignee } : {}),
        ...(newCase.tags !== undefined ? { tags: newCase.tags } : {}),
      };

      // Optimistically update the cache
      if (Object.keys(optimisticPatch).length > 0) {
        queryClient.setQueriesData<CaseRead | undefined>(
          { queryKey: queryKeys.case.detailBase(caseId), exact: false },
          (currentCase) => {
            if (!currentCase) return currentCase;
            return {
              ...currentCase,
              ...optimisticPatch,
            };
          }
        );
      }

      return { previousCases };
    },

    // On error, rollback to previous state
    onError: (error, _variables, context) => {
      if (context?.previousCases && context.previousCases.length > 0) {
        context.previousCases.forEach(([queryKey, previousCase]) => {
          queryClient.setQueryData(queryKey, previousCase);
        });
      }
      options?.onError?.(error);
    },

    // On success, invalidate queries to refetch fresh data
    onSuccess: async (data) => {
      if (caseId !== null) {
        // Use partial key matching to invalidate all queries with this case ID
        await queryClient.invalidateQueries({ queryKey: queryKeys.case.detailBase(caseId), exact: false });
        await queryClient.invalidateQueries({ queryKey: queryKeys.case.listBase() }); // Also invalidate the list
        await queryClient.refetchQueries({ queryKey: queryKeys.case.detailBase(caseId), exact: false, type: 'active' });
      }
      options?.onSuccess?.(data);
    },
  });
}
