import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { PropsWithChildren } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { CancelablePromise } from '@/types/generated/core/CancelablePromise';
import type { AlertRead } from '@/types/generated/models/AlertRead';
import { AlertsService } from '@/types/generated/services/AlertsService';
import { queryKeys } from './queryKeys';
import { useQuickTerminalSubmit } from './useQuickTerminalSubmit';

const draftKey = 'timeline-draft-alert-7-note';

afterEach(() => {
  localStorage.removeItem(draftKey);
  vi.restoreAllMocks();
});

it('reconciles a quick reply with the server ID and preserves the dock draft', async () => {
  const queryClient = new QueryClient();
  const queryKey = queryKeys.alert.detail(7, { includeLinkedTimelines: true });
  const timestamp = '2026-04-07T11:34:07Z';
  const parent = { id: 'parent', type: 'note', description: 'Parent', timestamp };
  const alert: AlertRead = {
    id: 7,
    human_id: 'ALT-0000007',
    title: 'Alert',
    priority: 'MEDIUM',
    status: 'NEW',
    created_at: timestamp,
    updated_at: timestamp,
    timeline_items: { parent },
  };
  queryClient.setQueryData(queryKey, alert);
  localStorage.setItem(draftKey, 'draft text');

  let resolveRequest!: (alert: AlertRead) => void;
  const request = new CancelablePromise<AlertRead>((resolve) => {
    resolveRequest = resolve;
  });
  const addTimelineItem = vi.spyOn(AlertsService, 'addTimelineItemApiV1AlertsAlertIdTimelinePost')
    .mockReturnValue(request);
  const wrapper = ({ children }: PropsWithChildren) =>
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  const { result } = renderHook(() => useQuickTerminalSubmit({ entityId: 7, entityType: 'alert' }), { wrapper });

  let pending!: ReturnType<typeof result.current.mutateAsync>;
  act(() => {
    pending = result.current.mutateAsync({ noteText: 'Reply', parentItemId: 'parent' });
  });
  await waitFor(() => {
    expect(result.current.isPending).toBe(true);
    expect(addTimelineItem).toHaveBeenCalledOnce();
  });

  const call = addTimelineItem.mock.calls[0][0];
  const { id } = call.requestBody as { id: string };
  expect(call).toMatchObject({
    alertId: 7,
    requestBody: { id: expect.any(String), description: 'Reply', type: 'note', parent_id: 'parent' },
  });
  expect(queryClient.getQueryData(queryKey)).toMatchObject({
    timeline_items: { parent: { replies: { [id]: { id, description: 'Reply', _optimistic: true } } } },
  });

  const reply = { id: 'server-reply', type: 'note', description: 'Reply', timestamp, parent_id: parent.id };
  const response: AlertRead = {
    ...alert,
    timeline_items: { parent: { ...parent, replies: { [reply.id]: reply } } },
  };
  await act(async () => {
    resolveRequest(response);
    await expect(pending).resolves.toEqual({ response, itemId: id });
  });
  expect(queryClient.getQueryData(queryKey)).toMatchObject({
    timeline_items: response.timeline_items,
  });
  const cached = queryClient.getQueryData<AlertRead>(queryKey);
  expect(cached?.timeline_items?.parent.replies).toEqual({ [reply.id]: reply });
  expect(localStorage.getItem(draftKey)).toBe('draft text');
});
