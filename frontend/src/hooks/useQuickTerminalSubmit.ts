/**
 * Hook for quick terminal note submission
 * 
 * Generic hook that works with different entity types (alerts, cases, tasks, etc.)
 * Handles optimistic updates and error recovery for timeline item creation.
 * 
 * @param entityId - The ID of the entity (alert, case, task, etc.)
 * @param entityType - The type of entity ("alert" | "case" | "task")
 * @returns TanStack Query mutation for submitting notes
 * 
 * @example
 * // Usage on Alerts page
 * const mutation = useQuickTerminalSubmit({ 
 *   entityId: alertId, 
 *   entityType: "alert" 
 * });
 * 
 * @example
 * // Usage on Tasks page
 * const mutation = useQuickTerminalSubmit({ 
 *   entityId: taskId, 
 *   entityType: "task" 
 * });
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { v4 as uuidv4 } from 'uuid';
import { AlertsService } from "@/types/generated/services/AlertsService";
import { CasesService } from "@/types/generated/services/CasesService";
import { TasksService } from "@/types/generated/services/TasksService";
import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { CaseReadWithAlerts } from "@/types/generated/models/CaseReadWithAlerts";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import type { EntityType } from "@/components/forms/QuickTerminal";
import { getEntityQueryKey } from './queryKeys';
import { createOptimisticTimelineItem, updateTimelineItemById } from '@/utils/timelineUtils';
import { getTimelineItemMap } from '@/utils/timelineHelpers';

interface UseQuickTerminalSubmitParams {
  entityId: number | null;
  entityType: EntityType;
}

export function useQuickTerminalSubmit({ entityId, entityType }: UseQuickTerminalSubmitParams) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ noteText, parentItemId }: { noteText: string; parentItemId?: string }) => {
      if (!entityId) {
        throw new Error(`No ${entityType} selected`);
      }

      // Generate UUID for the timeline item
      const itemId = uuidv4();

      const payload = {
        id: itemId,
        type: "note",
        description: noteText,
        timestamp: new Date().toISOString(),
        parent_id: parentItemId || null,
      };

      // Call appropriate service based on entity type
      let response;
      switch (entityType) {
        case "alert":
          response = await AlertsService.addTimelineItemApiV1AlertsAlertIdTimelinePost({
            alertId: entityId,
            requestBody: payload,
          });
          break;
        case "case":
          response = await CasesService.addTimelineItemApiV1CasesCaseIdTimelinePost({
            caseId: entityId,
            requestBody: payload,
          });
          break;
        case "task":
          response = await TasksService.addTimelineItemApiV1TasksTaskIdTimelinePost({
            taskId: entityId,
            requestBody: payload,
          });
          break;
        default:
          throw new Error(`Unsupported entity type: ${entityType}`);
      }

      return { response, itemId };
    },
    
    // Optimistic update: immediately add the note to the timeline before the server responds
    onMutate: async ({ noteText, parentItemId }: { noteText: string; parentItemId?: string }) => {
      if (entityId === null) return { previousEntity: undefined };

      const queryKey = getEntityQueryKey(entityType, entityId);

      // Cancel any outgoing refetches to prevent overwriting optimistic update
      // Use partial key matching for all entity types (they may have options like includeLinkedTimelines)
      await queryClient.cancelQueries({ queryKey, exact: false });

      // Snapshot the previous value for rollback
      // Use partial key matching to handle query keys with options
      const queriesData = queryClient.getQueriesData<AlertRead | CaseReadWithAlerts | TaskRead>({ queryKey, exact: false });
      const previousEntity: AlertRead | CaseReadWithAlerts | TaskRead | undefined =
        queriesData.length > 0 ? queriesData[0][1] : undefined;

      // Create optimistic timeline item using shared utility
      if (previousEntity) {
        const optimisticItem = createOptimisticTimelineItem({
          type: "note",
          description: noteText,
          timestamp: new Date().toISOString(),
          parent_id: parentItemId || null,
        });
        const optimisticItemId = optimisticItem.id;

        if (!optimisticItemId) {
          return { previousEntity };
        }

        const previousTimeline = getTimelineItemMap(previousEntity);

        const nextTimeline = parentItemId
          ? updateTimelineItemById(previousTimeline, parentItemId, {
              replies: {
                ...((previousTimeline[parentItemId]?.replies as Record<string, unknown> | null | undefined) ?? {}),
                [optimisticItemId]: optimisticItem,
              } as any,
            })
          : {
              ...previousTimeline,
              [optimisticItemId]: optimisticItem,
            };
        
        const updatedEntity = {
          ...previousEntity,
          timeline_items: nextTimeline as any,
        };
        
        // Use partial key matching for all entity types (they may have options like includeLinkedTimelines)
        queryClient.setQueriesData({ queryKey, exact: false }, updatedEntity);
      }

      // Return context with the previous value for rollback
      return { previousEntity };
    },

    // On error, roll back the optimistic update
    onError: (error, _variables, context) => {
      if (context?.previousEntity && entityId !== null) {
        const queryKey = getEntityQueryKey(entityType, entityId);
        // Use partial key matching for all entity types (they may have options like includeLinkedTimelines)
        queryClient.setQueriesData({ queryKey, exact: false }, context.previousEntity);
      }
      console.error('Failed to add timeline item:', error);
    },

    // On success, replace optimistic update with real server data
    onSuccess: (data) => {
      if (entityId !== null) {
        const queryKey = getEntityQueryKey(entityType, entityId);
        // Use partial key matching for all entity types (they may have options like includeLinkedTimelines)
        queryClient.setQueriesData({ queryKey, exact: false }, data.response);
      }
    },
  });
}
