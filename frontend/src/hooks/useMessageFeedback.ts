import { useMutation, useQueryClient } from '@tanstack/react-query';
import { LangflowService } from '@/types/generated/services/LangflowService';
import type { LangFlowMessageRead } from '@/types/generated/models/LangFlowMessageRead';
import type { MessageFeedback } from '@/types/generated/models/MessageFeedback';
import { queryKeys } from './queryKeys';

interface UseMessageFeedbackOptions {
  onSuccess?: (data: LangFlowMessageRead) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook to set feedback on a chat message
 * 
 * @param options - Optional callbacks for success/error handling
 * @returns Mutation object with setFeedback and clearFeedback functions
 */
export function useMessageFeedback(options?: UseMessageFeedbackOptions) {
  const queryClient = useQueryClient();

  const setFeedbackMutation = useMutation<
    LangFlowMessageRead,
    Error,
    { messageId: string; feedback: MessageFeedback }
  >({
    mutationFn: async ({ messageId, feedback }) => {
      return LangflowService.setMessageFeedbackApiV1LangflowMessagesMessageIdFeedbackPatch({
        messageId,
        requestBody: { feedback },
      });
    },
    onSuccess: (data) => {
      // Invalidate session messages to reflect the update
      queryClient.invalidateQueries({ queryKey: ['langflow', 'sessions'] });
      options?.onSuccess?.(data);
    },
    onError: (error) => {
      options?.onError?.(error);
    },
  });

  const clearFeedbackMutation = useMutation<LangFlowMessageRead, Error, { messageId: string }>({
    mutationFn: async ({ messageId }) => {
      return LangflowService.clearMessageFeedbackApiV1LangflowMessagesMessageIdFeedbackDelete({
        messageId,
      });
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['langflow', 'sessions'] });
      options?.onSuccess?.(data);
    },
    onError: (error) => {
      options?.onError?.(error);
    },
  });

  return {
    setFeedback: setFeedbackMutation.mutate,
    clearFeedback: clearFeedbackMutation.mutate,
    isSettingFeedback: setFeedbackMutation.isPending,
    isClearingFeedback: clearFeedbackMutation.isPending,
    setFeedbackError: setFeedbackMutation.error,
    clearFeedbackError: clearFeedbackMutation.error,
  };
}
