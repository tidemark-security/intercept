/**
 * Hooks for fetching AI drill-down data (triage recommendations and chat feedback messages)
 */
import { useQuery } from '@tanstack/react-query';
import { MetricsService } from '@/types/generated/services/MetricsService';
import type { 
  TriageRecommendationDrillDownResponse, 
  ChatFeedbackDrillDownResponse,
  RejectionCategory,
  TriageDisposition,
  RecommendationStatus,
  MessageFeedback,
} from '@/types/generated';

interface UseTriageDrillDownParams {
  start?: string;
  end?: string;
  disposition?: TriageDisposition;
  rejection_category?: RejectionCategory;
  status?: RecommendationStatus;
  limit?: number;
  offset?: number;
  enabled?: boolean;
}

interface UseChatFeedbackDrillDownParams {
  start?: string;
  end?: string;
  feedback?: MessageFeedback;
  limit?: number;
  offset?: number;
  enabled?: boolean;
}

/**
 * Fetch triage recommendations with filters for drill-down view
 */
export function useTriageDrillDown({
  start,
  end,
  disposition,
  rejection_category,
  status,
  limit = 50,
  offset = 0,
  enabled = true,
}: UseTriageDrillDownParams) {
  return useQuery<TriageRecommendationDrillDownResponse>({
    queryKey: ['ai-triage-drilldown', start, end, disposition, rejection_category, status, limit, offset],
    queryFn: async () => {
      return await MetricsService.getAiTriageRecommendationsDrilldownApiV1MetricsAiTriageRecommendationsGet({
        disposition: disposition ?? undefined,
        rejectionCategory: rejection_category ?? undefined,
        status: status ?? undefined,
        start: start ?? undefined,
        end: end ?? undefined,
        limit,
        offset,
      });
    },
    enabled: enabled && !!start && !!end,
  });
}

/**
 * Fetch chat messages with feedback for drill-down view
 */
export function useChatFeedbackDrillDown({
  start,
  end,
  feedback,
  limit = 50,
  offset = 0,
  enabled = true,
}: UseChatFeedbackDrillDownParams) {
  return useQuery<ChatFeedbackDrillDownResponse>({
    queryKey: ['ai-chat-drilldown', start, end, feedback, limit, offset],
    queryFn: async () => {
      return await MetricsService.getAiChatFeedbackDrilldownApiV1MetricsAiChatFeedbackMessagesGet({
        feedback: feedback ?? undefined,
        start: start ?? undefined,
        end: end ?? undefined,
        limit,
        offset,
      });
    },
    enabled: enabled && !!start && !!end,
  });
}
