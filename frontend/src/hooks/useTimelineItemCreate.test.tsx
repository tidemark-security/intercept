import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { addCaseTimelineItem } = vi.hoisted(() => ({
  addCaseTimelineItem: vi.fn(),
}));

const { addAlertTimelineItem } = vi.hoisted(() => ({
  addAlertTimelineItem: vi.fn(),
}));

const { addTaskTimelineItem } = vi.hoisted(() => ({
  addTaskTimelineItem: vi.fn(),
}));

vi.mock('@/types/generated/services/AlertsService', () => ({
  AlertsService: {
    addTimelineItemApiV1AlertsAlertIdTimelinePost: addAlertTimelineItem,
  },
}));

vi.mock('@/types/generated/services/CasesService', () => ({
  CasesService: {
    addTimelineItemApiV1CasesCaseIdTimelinePost: addCaseTimelineItem,
  },
}));

vi.mock('@/types/generated/services/TasksService', () => ({
  TasksService: {
    addTimelineItemApiV1TasksTaskIdTimelinePost: addTaskTimelineItem,
  },
}));

import { queryKeys } from './queryKeys';
import { useTimelineItemCreate } from './useTimelineItemCreate';

type TestEntity = {
  label: string;
  context: 'alert' | 'case' | 'task';
  entityId: number;
  queryKey: readonly unknown[];
  detail: Record<string, unknown>;
  serviceMock: ReturnType<typeof vi.fn>;
};

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useTimelineItemCreate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each<TestEntity>([
    {
      label: 'alert',
      context: 'alert',
      entityId: 7,
      queryKey: queryKeys.alert.detail(7, { includeLinkedTimelines: true }),
      detail: {
        id: 7,
        human_id: 'ALT-0000007',
        title: 'Alert',
        description: 'Alert description',
        status: 'NEW',
        priority: 'MEDIUM',
        source: 'SIEM',
        assignee: null,
        case_id: null,
        linked_at: null,
        triaged_at: null,
        triage_notes: null,
        created_at: '2026-04-07T11:34:07Z',
        updated_at: '2026-04-07T11:34:07Z',
        tags: [],
        timeline_items: {},
        triage_recommendation: null,
      },
      serviceMock: addAlertTimelineItem,
    },
    {
      label: 'case',
      context: 'case',
      entityId: 2,
      queryKey: queryKeys.case.detail(2, { includeLinkedTimelines: true }),
      detail: {
        id: 2,
        human_id: 'CAS-0000002',
        title: 'Case',
        description: 'Case description',
        status: 'NEW',
        priority: 'MEDIUM',
        created_by: 'admin',
        assignee: null,
        created_at: '2026-04-07T11:34:07Z',
        updated_at: '2026-04-07T11:34:07Z',
        closed_at: null,
        tags: [],
        timeline_items: {},
      },
      serviceMock: addCaseTimelineItem,
    },
    {
      label: 'task',
      context: 'task',
      entityId: 11,
      queryKey: queryKeys.task.detail(11, { includeLinkedTimelines: true }),
      detail: {
        id: 11,
        human_id: 'TSK-0000011',
        title: 'Task',
        description: 'Task description',
        status: 'TODO',
        priority: 'MEDIUM',
        created_by: 'admin',
        assignee: null,
        case_id: null,
        linked_at: null,
        due_date: null,
        created_at: '2026-04-07T11:34:07Z',
        updated_at: '2026-04-07T11:34:07Z',
        tags: [],
        timeline_items: {},
      },
      serviceMock: addTaskTimelineItem,
    },
  ])('optimistically adds $label timeline items when cached timeline_items is an object map', async ({
    context,
    entityId,
    queryKey,
    detail,
    serviceMock,
  }) => {
    const deferred = createDeferred<any>();
    serviceMock.mockReturnValue(deferred.promise);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    queryClient.setQueryData(queryKey, detail);

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useTimelineItemCreate(entityId, { context }),
      { wrapper },
    );

    let mutationPromise: Promise<unknown> | undefined;
    const payload = {
      id: 'observable-1',
      type: 'observable',
      observable_type: 'IP',
      observable_value: '1.1.1.1',
      description: 'Optimistic observable',
    };

    await act(async () => {
      mutationPromise = result.current.mutateAsync(payload);
    });

    await waitFor(() => {
      const optimisticCase = queryClient.getQueryData<any>(
        queryKey,
      );

      expect(optimisticCase.timeline_items['observable-1']).toMatchObject({
        id: 'observable-1',
        type: 'observable',
        observable_type: 'IP',
        observable_value: '1.1.1.1',
        _optimistic: true,
      });
    });

    await act(async () => {
      deferred.resolve({
        ...detail,
        timeline_items: {
          'observable-1': {
            id: 'observable-1',
            type: 'observable',
            observable_type: 'IP',
            observable_value: '1.1.1.1',
            description: 'Optimistic observable',
          },
        },
      });

      await mutationPromise;
    });
  });
});