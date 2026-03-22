import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { TasksService } from '@/types/generated/services/TasksService';
import type { TaskUpdate } from '@/types/generated/models/TaskUpdate';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import { queryKeys } from './queryKeys';

interface UseUpdateTaskOptions {
  onSuccess?: (data: TaskRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to update a task using TanStack Query mutation
 * Provides optimistic updates, automatic query invalidation, and error handling
 * 
 * @param taskId - The ID of the task to update
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useUpdateTask(
  taskId: number | null,
  options?: UseUpdateTaskOptions
): UseMutationResult<TaskRead, Error, TaskUpdate, { previousTask: TaskRead | undefined }> {
  const queryClient = useQueryClient();

  return useMutation<TaskRead, Error, TaskUpdate, { previousTask: TaskRead | undefined }>({
    mutationFn: async (taskUpdate: TaskUpdate) => {
      if (taskId === null) {
        throw new Error('Task ID is required');
      }
      return TasksService.updateTaskApiV1TasksTaskIdPut({
        taskId,
        requestBody: taskUpdate,
      });
    },
    
    // Optimistic update: immediately update the cache before the mutation completes
    onMutate: async (newTask: TaskUpdate) => {
      if (taskId === null) return { previousTask: undefined };

      // Cancel any outgoing refetches to prevent overwriting optimistic update
      // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
      await queryClient.cancelQueries({ queryKey: queryKeys.task.detailBase(taskId), exact: false });

      // Snapshot the previous value for rollback
      // Use partial key matching to handle query keys with options
      const queriesData = queryClient.getQueriesData<TaskRead>({ queryKey: queryKeys.task.detailBase(taskId), exact: false });
      const previousTask = queriesData.length > 0 ? queriesData[0][1] : undefined;

      // Optimistically update the cache
      if (previousTask) {
        const updatedTask: TaskRead = {
          ...previousTask,
          ...Object.fromEntries(
            Object.entries(newTask).filter(([_, value]) => value !== null && value !== undefined)
          ),
        };
        queryClient.setQueriesData<TaskRead>({ queryKey: queryKeys.task.detailBase(taskId), exact: false }, updatedTask);
      }

      return { previousTask };
    },

    // On error, rollback to previous state
    onError: (error, _variables, context) => {
      if (context?.previousTask && taskId !== null) {
        queryClient.setQueriesData({ queryKey: queryKeys.task.detailBase(taskId), exact: false }, context.previousTask);
      }
      options?.onError?.(error);
    },

    // On success, invalidate queries to refetch fresh data
    // Use partial key matching to handle query keys with options like { includeLinkedTimelines }
    onSuccess: (data) => {
      if (taskId !== null) {
        queryClient.invalidateQueries({ queryKey: queryKeys.task.detailBase(taskId), exact: false });
        queryClient.invalidateQueries({ queryKey: queryKeys.task.listBase() }); // Also invalidate the list
      }
      options?.onSuccess?.(data);
    },
  });
}
