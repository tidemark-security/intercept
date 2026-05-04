import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getCaseGraph, patchCaseGraph, getTaskGraph, patchTaskGraph } = vi.hoisted(() => ({
  getCaseGraph: vi.fn(),
  patchCaseGraph: vi.fn(),
  getTaskGraph: vi.fn(),
  patchTaskGraph: vi.fn(),
}));

vi.mock('@/types/generated/services/CasesService', () => ({
  CasesService: {
    getTimelineGraphApiV1CasesCaseIdTimelineGraphGet: getCaseGraph,
    patchTimelineGraphApiV1CasesCaseIdTimelineGraphPatch: patchCaseGraph,
  },
}));

vi.mock('@/types/generated/services/TasksService', () => ({
  TasksService: {
    getTimelineGraphApiV1TasksTaskIdTimelineGraphGet: getTaskGraph,
    patchTimelineGraphApiV1TasksTaskIdTimelineGraphPatch: patchTaskGraph,
  },
}));

import { queryKeys } from './queryKeys';
import { usePatchTimelineGraph, useTimelineGraph } from './useTimelineGraph';

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useTimelineGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads case graph state from the API', async () => {
    getCaseGraph.mockResolvedValue({
      entity_type: 'case',
      entity_id: 3,
      revision: 0,
      graph: { nodes: {}, edges: {} },
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    const { result } = renderHook(() => useTimelineGraph('case', 3), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getCaseGraph).toHaveBeenCalledWith({ caseId: 3 });
    expect(result.current.data?.graph).toEqual({ nodes: {}, edges: {} });
  });

  it('patches task graph state and replaces cached graph on success', async () => {
    patchTaskGraph.mockResolvedValue({
      entity_type: 'task',
      entity_id: 8,
      revision: 1,
      graph: {
        nodes: {
          'node-note-1': { id: 'node-note-1', item_id: 'note-1', position: { x: 20, y: 40 } },
        },
        edges: {},
      },
    });
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    queryClient.setQueryData(queryKeys.task.graph(8), {
      entity_type: 'task',
      entity_id: 8,
      revision: 0,
      graph: { nodes: {}, edges: {} },
    });

    const { result } = renderHook(() => usePatchTimelineGraph('task', 8), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({
        base_revision: 0,
        operations: [{ type: 'add_node', node_id: 'node-note-1', item_id: 'note-1', position: { x: 20, y: 40 } }],
      });
    });

    expect(patchTaskGraph).toHaveBeenCalledWith({
      taskId: 8,
      requestBody: {
        base_revision: 0,
        operations: [{ type: 'add_node', node_id: 'node-note-1', item_id: 'note-1', position: { x: 20, y: 40 } }],
      },
    });
    expect(queryClient.getQueryData<any>(queryKeys.task.graph(8)).revision).toBe(1);
  });
});