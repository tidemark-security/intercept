import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { updateCaseTimelineItem } = vi.hoisted(() => ({
  updateCaseTimelineItem: vi.fn(),
}));

vi.mock('@/types/generated/services/AlertsService', () => ({
  AlertsService: { updateTimelineItemApiV1AlertsAlertIdTimelineItemIdPut: vi.fn() },
}));

vi.mock('@/types/generated/services/CasesService', () => ({
  CasesService: { updateTimelineItemApiV1CasesCaseIdTimelineItemIdPut: updateCaseTimelineItem },
}));

vi.mock('@/types/generated/services/TasksService', () => ({
  TasksService: { updateTimelineItemApiV1TasksTaskIdTimelineItemIdPut: vi.fn() },
}));

import { queryKeys } from './queryKeys';
import { useUpdateTimelineItem } from './useUpdateTimelineItem';

const attachment = {
  id: 'attachment-1',
  type: 'attachment',
  created_at: '2026-10-25T23:13:38Z',
  created_by: 'analyst',
  timestamp: '2026-10-25T23:13:38Z',
  description: null,
  tags: [],
  file_name: 'evidence.html',
  mime_type: 'text/html',
  file_size: 1619844,
  upload_status: 'COMPLETE',
  replies: {
    'reply-1': { id: 'reply-1', type: 'note', description: 'Existing reply' },
  },
};

function renderUpdateHook() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  queryClient.setQueryData(queryKeys.case.detailBase(15301), {
    id: 15301,
    timeline_items: { [attachment.id]: attachment },
  });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useUpdateTimelineItem(15301, 'case'), { wrapper });
}

describe('useUpdateTimelineItem', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateCaseTimelineItem.mockResolvedValue({ id: 15301, timeline_items: {} });
  });

  // The backend rejects any update carrying created_at (400 "created_at is immutable"),
  // and a replies payload would overwrite nested replies. See docs/attachment-lifecycle.md.
  it('sends the cached item merged with updates, without created_at or replies', async () => {
    const { result } = renderUpdateHook();

    await act(async () => {
      await result.current.mutateAsync({
        itemId: 'attachment-1',
        updates: {
          type: 'attachment',
          created_at: attachment.created_at,
          replies: {},
          description: 'Edited description',
          timestamp: '2026-10-26T11:51:00',
          tags: ['edited'],
        },
      });
    });

    expect(updateCaseTimelineItem).toHaveBeenCalledTimes(1);
    const { caseId, itemId, requestBody } = updateCaseTimelineItem.mock.calls[0][0];
    expect(caseId).toBe(15301);
    expect(itemId).toBe('attachment-1');
    expect(requestBody).not.toHaveProperty('created_at');
    expect(requestBody).not.toHaveProperty('replies');
    expect(requestBody).toMatchObject({
      id: 'attachment-1',
      type: 'attachment',
      description: 'Edited description',
      timestamp: '2026-10-26T11:51:00',
      tags: ['edited'],
      file_name: 'evidence.html',
      created_by: 'analyst',
    });
  });
});
