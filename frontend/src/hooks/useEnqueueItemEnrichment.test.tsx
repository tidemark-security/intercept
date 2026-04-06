import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const enqueueItemEnrichment = vi.hoisted(() => vi.fn());

vi.mock('@/types/generated/services/EnrichmentsService', () => ({
  EnrichmentsService: {
    enqueueItemEnrichmentApiV1EnrichmentsEntityTypeEntityIdItemsItemIdEnqueuePost: enqueueItemEnrichment,
  },
}));

import { useEnqueueItemEnrichment } from './useEnqueueItemEnrichment';

describe('useEnqueueItemEnrichment', () => {
  beforeEach(() => {
    enqueueItemEnrichment.mockReset();
    enqueueItemEnrichment.mockResolvedValue({ enqueued: true, task_id: 'task-123' });
  });

  it('waits briefly before enqueueing the refresh request', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const onSuccess = vi.fn();
    queryClient.setQueryData(['case', 1, {}], {
      id: 1,
      timeline_items: [
        {
          id: 'item-1',
          type: 'internal_actor',
          user_id: 'alice@example.com',
          enrichment_status: 'failed',
        },
      ],
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () => useEnqueueItemEnrichment('case', 1, { onSuccess }),
      { wrapper },
    );

    const startedAt = Date.now();
    let mutationPromise: Promise<unknown>;
    act(() => {
      mutationPromise = result.current.mutateAsync({ itemId: 'item-1' });
    });

    await waitFor(() => {
      expect(queryClient.getQueryData<{ timeline_items: Array<{ enrichment_status?: string }> }>(['case', 1, {}])?.timeline_items[0]?.enrichment_status).toBe('pending');
    });
    await act(async () => {
      await mutationPromise;
    });

    expect(enqueueItemEnrichment).toHaveBeenCalledWith({
      entityType: 'case',
      entityId: 1,
      itemId: 'item-1',
    });
    expect(Date.now() - startedAt).toBeGreaterThanOrEqual(450);
    expect(queryClient.getQueryData<{ timeline_items: Array<{ enrichment_task_id?: string | null }> }>(['case', 1, {}])?.timeline_items[0]?.enrichment_task_id).toBe('task-123');
    expect(onSuccess).toHaveBeenCalledWith('task-123');
  });
});