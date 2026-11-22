import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CasesService } from '@/types/generated/services/CasesService';
import type { CaseRead } from '@/types/generated/models/CaseRead';
import type { CancelablePromise } from '@/types/generated/core/CancelablePromise';
import type { TimelineItem } from '@/types/timeline';
import { getQueueSearchQueryKey, queryKeys } from './queryKeys';
import { useDeleteTimelineItem } from './useDeleteTimelineItem';
import { useTimelineItemCreate } from './useTimelineItemCreate';
import { useUpdateTimelineItem } from './useUpdateTimelineItem';

const caseId = 7;
const plainKey = queryKeys.case.detail(caseId, { includeLinkedTimelines: false });
const linkedKey = queryKeys.case.detail(caseId, { includeLinkedTimelines: true });
const queueKey = getQueueSearchQueryKey('case');
const note = { id: 'note', type: 'note', description: 'Original', flagged: false };
const link = { id: 'link', type: 'alert', replies: { note } };
const source = { origin: { id: 'origin', type: 'note', description: 'From the alert' } };
const plain = {
  id: caseId,
  title: 'Plain',
  status: 'NEW',
  human_id: 'CAS-0000007',
  created_by: 'analyst',
  created_at: '2026-11-22T00:00:00Z',
  updated_at: '2026-11-22T00:00:00Z',
  timeline_items: { link },
} satisfies CaseRead;
const linked = {
  ...plain,
  title: 'Expanded',
  alerts: [{ id: 8 }],
  timeline_items: { link: { ...link, source_timeline_items: source } },
};

function renderMutations() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  client.setQueryData(plainKey, plain);
  client.setQueryData(linkedKey, linked);
  client.setQueryData(queueKey, []);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => ({
    create: useTimelineItemCreate(caseId, { context: 'case', parentItemId: 'link' }),
    update: useUpdateTimelineItem(caseId, 'case'),
    delete: useDeleteTimelineItem(caseId, 'case'),
  }), { wrapper });

  function read(key: typeof plainKey) {
    return client.getQueryData<Omit<typeof linked, 'timeline_items'> & { timeline_items: Record<string, TimelineItem> }>(key)!;
  }

  return { client, result, read };
}

function deferredResponse() {
  let resolve!: (value: CaseRead) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<CaseRead>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise: promise as CancelablePromise<CaseRead>, resolve, reject };
}

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('timeline mutation cache', () => {
  it('replaces a temporary reply with its server ID and clears only the case draft', async () => {
    const response = deferredResponse();
    vi.spyOn(CasesService, 'addTimelineItemApiV1CasesCaseIdTimelinePost')
      .mockReturnValue(response.promise);
    const { client, result, read } = renderMutations();
    localStorage.setItem('timeline-draft-case-7-note', 'case draft');
    localStorage.setItem('timeline-draft-alert-7-note', 'alert draft');

    let mutation: Promise<unknown>;
    await act(async () => {
      mutation = result.current.create.mutateAsync({ id: 'temp', type: 'note', description: 'A reply' });
    });
    for (const key of [plainKey, linkedKey]) {
      expect(read(key).timeline_items.link.replies).toMatchObject({ temp: { parent_id: 'link', _optimistic: true } });
    }
    expect(read(linkedKey).timeline_items.link.source_timeline_items).toEqual(source);

    await act(async () => {
      const reply = { id: 'saved', type: 'note', parent_id: 'link', description: 'A reply' };
      response.resolve({ ...plain, timeline_items: { link: { ...link, replies: { note, saved: reply } } } });
      await mutation;
    });
    expect(read(plainKey)).toMatchObject({ title: 'Plain', timeline_items: { link: { replies: { saved: { id: 'saved' } } } } });
    expect(read(plainKey).timeline_items.link).not.toHaveProperty('source_timeline_items');
    expect(read(linkedKey)).toMatchObject({ title: 'Expanded', alerts: [{ id: 8 }] });
    expect(read(linkedKey).timeline_items.link).toMatchObject({
      source_timeline_items: source,
      replies: { saved: { id: 'saved' }, note },
    });
    expect(read(linkedKey).timeline_items.link.replies).not.toHaveProperty('temp');
    expect(client.getQueryState(queueKey)?.isInvalidated).toBe(true);
    expect(localStorage.getItem('timeline-draft-case-7-note')).toBeNull();
    expect(localStorage.getItem('timeline-draft-alert-7-note')).toBe('alert draft');
  });

  it('rolls back a failed field while keeping a later edit visible and out of the failed request', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const first = deferredResponse();
    const second = deferredResponse();
    const update = vi.spyOn(CasesService, 'updateTimelineItemApiV1CasesCaseIdTimelineItemIdPut')
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { client, result, read } = renderMutations();
    const freshNote = { ...note, description: 'Latest server description' };
    const oldTimestamp = '2026-11-22T00:00:00Z';
    const newTimestamp = '2026-11-22T00:01:00Z';
    client.setQueryData(plainKey, { ...plain, updated_at: oldTimestamp });
    client.setQueryData(linkedKey, {
      ...linked,
      updated_at: newTimestamp,
      timeline_items: { link: { ...linked.timeline_items.link, replies: { note: freshNote } } },
    });

    let failed: Promise<unknown>;
    let saved: Promise<unknown>;
    await act(async () => {
      failed = result.current.update.mutateAsync({ itemId: 'note', updates: { description: 'Will fail' } }).catch((error) => error);
      saved = result.current.update.mutateAsync({ itemId: 'note', updates: { flagged: true } });
    });
    expect(read(linkedKey).timeline_items.link.replies?.note).toMatchObject({ description: 'Will fail', flagged: true });
    expect(update).toHaveBeenCalledTimes(1);
    expect(update.mock.calls[0][0].requestBody).toMatchObject({ flagged: false });

    await act(async () => {
      first.reject(new Error('Update failed'));
      await failed;
    });
    await waitFor(() => expect(update).toHaveBeenCalledTimes(2));
    expect(update.mock.calls[1][0].requestBody).toMatchObject({ description: 'Latest server description', flagged: true });
    expect(read(plainKey).timeline_items.link.replies?.note).toMatchObject({ description: 'Original', flagged: true });
    expect(read(linkedKey).timeline_items.link.replies?.note).toMatchObject({ description: 'Latest server description', flagged: true });

    await act(async () => {
      const savedNote = { ...freshNote, flagged: true, audit: { edited: true } };
      second.resolve({
        ...plain,
        updated_at: newTimestamp,
        timeline_items: { link: { ...link, replies: { note: savedNote } } },
      });
      await saved;
    });
    expect(read(linkedKey).timeline_items.link.source_timeline_items).toEqual(source);
    expect(read(linkedKey).timeline_items.link.replies?.note?.audit).toEqual({ edited: true });
    expect(read(plainKey)).toHaveProperty('updated_at', oldTimestamp);
    expect(client.getQueryState(queueKey)?.isInvalidated).toBe(true);
  });

  it('removes a failed create from a view independently patched while it was pending', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const response = deferredResponse();
    vi.spyOn(CasesService, 'addTimelineItemApiV1CasesCaseIdTimelinePost').mockReturnValue(response.promise);
    const { client, result, read } = renderMutations();
    localStorage.setItem('timeline-draft-case-7-note', 'case draft');
    let mutation: Promise<unknown>;
    await act(async () => {
      mutation = result.current.create.mutateAsync({ id: 'temp', type: 'note' }).catch((error) => error);
    });

    const visible = read(linkedKey);
    const parent = visible.timeline_items.link;
    client.setQueryData(linkedKey, {
      ...visible,
      timeline_items: {
        link: { ...parent, replies: { ...parent.replies, note: { ...note, enrichment_status: 'pending' } } },
      },
    });

    await act(async () => {
      response.reject(new Error('Create failed'));
      await mutation;
    });
    expect(read(linkedKey).timeline_items.link.replies).toEqual({ note: { ...note, enrichment_status: 'pending' } });
    expect(read(plainKey).timeline_items.link.replies).toEqual({ note });
    expect(localStorage.getItem('timeline-draft-case-7-note')).toBe('case draft');
  });

  it('keeps a delete pending across a refetch and restores the latest reply on failure', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const response = deferredResponse();
    vi.spyOn(CasesService, 'removeTimelineItemApiV1CasesCaseIdTimelineItemIdDelete')
      .mockReturnValue(response.promise);
    const { client, result, read } = renderMutations();

    let mutation: Promise<unknown>;
    await act(async () => {
      mutation = result.current.delete.mutateAsync({ itemId: 'note' }).catch((error) => error);
    });
    for (const key of [plainKey, linkedKey]) {
      expect(read(key).timeline_items.link.replies).not.toHaveProperty('note');
    }

    const changed = { ...note, description: 'Edited while the delete was pending' };
    await act(async () => {
      await client.fetchQuery({
        queryKey: linkedKey,
        queryFn: async () => ({
          ...linked,
          title: 'Refetched',
          timeline_items: { link: { ...linked.timeline_items.link, replies: { note: changed } } },
        }),
      });
    });
    expect(read(linkedKey).title).toBe('Refetched');
    expect(read(linkedKey).timeline_items.link.replies).not.toHaveProperty('note');

    await act(async () => {
      response.reject(new Error('Delete failed'));
      await mutation;
    });
    expect(read(linkedKey).timeline_items.link.replies?.note).toEqual(changed);
    expect(read(plainKey).timeline_items.link.replies?.note).toEqual(note);
    expect(client.getQueryState(queueKey)?.isInvalidated).toBe(false);
  });

  it('keeps the server tombstone in its reply thread without removing the linked expansion', async () => {
    const tombstone = { id: 'note', type: '_deleted', parent_id: 'link', original_type: 'note' };
    const response = { ...plain, timeline_items: { link: { ...link, replies: { note: tombstone } } } };
    const request = deferredResponse();
    vi.spyOn(CasesService, 'removeTimelineItemApiV1CasesCaseIdTimelineItemIdDelete').mockReturnValue(request.promise);
    const { client, result, read } = renderMutations();

    await act(async () => {
      request.resolve(response);
      await result.current.delete.mutateAsync({ itemId: 'note' });
    });

    for (const key of [plainKey, linkedKey]) {
      expect(read(key).timeline_items.link.replies?.note).toEqual(tombstone);
    }
    expect(read(linkedKey).timeline_items.link.source_timeline_items).toEqual(source);
    expect(client.getQueryState(queueKey)?.isInvalidated).toBe(true);
  });
});
