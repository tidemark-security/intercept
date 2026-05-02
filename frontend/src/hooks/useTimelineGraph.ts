import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';
import type { TimelineGraphPatch } from '@/types/generated/models/TimelineGraphPatch';
import type { TimelineGraphRead } from '@/types/generated/models/TimelineGraphRead';
import { CasesService } from '@/types/generated/services/CasesService';
import { TasksService } from '@/types/generated/services/TasksService';
import { QUERY_STALE_TIMES } from '@/config/queryConfig';
import { queryKeys } from './queryKeys';

export type TimelineGraphEntityType = 'case' | 'task';

function getGraphQueryKey(entityType: TimelineGraphEntityType, entityId: number | null) {
  return entityType === 'case'
    ? queryKeys.case.graph(entityId)
    : queryKeys.task.graph(entityId);
}

function getGraphQueryBase(entityType: TimelineGraphEntityType, entityId: number) {
  return entityType === 'case'
    ? queryKeys.case.graphBase(entityId)
    : queryKeys.task.graphBase(entityId);
}

async function fetchTimelineGraph(entityType: TimelineGraphEntityType, entityId: number): Promise<TimelineGraphRead> {
  if (entityType === 'case') {
    return CasesService.getTimelineGraphApiV1CasesCaseIdTimelineGraphGet({ caseId: entityId });
  }

  return TasksService.getTimelineGraphApiV1TasksTaskIdTimelineGraphGet({ taskId: entityId });
}

async function patchTimelineGraph(
  entityType: TimelineGraphEntityType,
  entityId: number,
  patch: TimelineGraphPatch,
): Promise<TimelineGraphRead> {
  if (entityType === 'case') {
    return CasesService.patchTimelineGraphApiV1CasesCaseIdTimelineGraphPatch({ caseId: entityId, requestBody: patch });
  }

  return TasksService.patchTimelineGraphApiV1TasksTaskIdTimelineGraphPatch({ taskId: entityId, requestBody: patch });
}

export function useTimelineGraph(entityType: TimelineGraphEntityType, entityId: number | null) {
  return useQuery<TimelineGraphRead, Error>({
    queryKey: getGraphQueryKey(entityType, entityId),
    queryFn: async () => {
      if (entityId === null) {
        throw new Error('Entity ID is required');
      }
      return fetchTimelineGraph(entityType, entityId);
    },
    enabled: entityId !== null,
    staleTime: QUERY_STALE_TIMES.REALTIME,
  });
}

export function usePatchTimelineGraph(
  entityType: TimelineGraphEntityType,
  entityId: number | null,
): UseMutationResult<TimelineGraphRead, Error, TimelineGraphPatch> {
  const queryClient = useQueryClient();

  return useMutation<TimelineGraphRead, Error, TimelineGraphPatch>({
    mutationFn: async (patch) => {
      if (entityId === null) {
        throw new Error('Entity ID is required');
      }
      return patchTimelineGraph(entityType, entityId, patch);
    },
    onSuccess: (graph) => {
      if (entityId === null) return;
      queryClient.setQueryData(getGraphQueryKey(entityType, entityId), graph);
    },
    onError: () => {
      if (entityId === null) return;
      queryClient.invalidateQueries({ queryKey: getGraphQueryBase(entityType, entityId), exact: false });
    },
  });
}