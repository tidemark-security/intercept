import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { TasksService } from '@/types/generated/services/TasksService';
import type { TaskCreate } from '@/types/generated/models/TaskCreate';
import type { TaskRead } from '@/types/generated/models/TaskRead';
import { queryKeys } from './queryKeys';

interface UseCreateTaskOptions {
  onSuccess?: (data: TaskRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to create a new task using TanStack Query mutation
 * 
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with mutate, isPending, isError, error, and data properties
 */
export function useCreateTask(
  options?: UseCreateTaskOptions
): UseMutationResult<TaskRead, Error, TaskCreate, unknown> {
  const queryClient = useQueryClient();

  return useMutation<TaskRead, Error, TaskCreate, unknown>({
    mutationFn: async (taskCreate: TaskCreate) => {
      return TasksService.createTaskApiV1TasksPost({
        requestBody: taskCreate,
      });
    },

    // On success, invalidate queries to refetch fresh data
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.task.listBase() });
      options?.onSuccess?.(data);
    },

    // On error, call error callback
    onError: (error) => {
      options?.onError?.(error);
    },
  });
}
