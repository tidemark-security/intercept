import type { QueryClient, QueryKey } from '@tanstack/react-query';
import type { TimelineItem } from '@/types/timeline';
import { getTimelineItemMap } from '@/utils/timelineHelpers';
import {
  findTimelineItem,
  removeTimelineItemById,
  updateTimelineItemById,
  type TimelineItemCollection,
  type TimelineItemMap,
} from '@/utils/timelineUtils';
import { getEntityQueryKey, type EntityType } from './queryKeys';

type TimelineChange =
  | { type: 'create'; parentId: string | null; item?: TimelineItem }
  | { type: 'update'; itemId: string; updates: Partial<TimelineItem> }
  | { type: 'delete'; itemId: string };

export type TimelineMutationContext = TimelineChange | undefined;

type TimelineDetails = { timeline_items?: TimelineItemCollection; updated_at?: string };
type TimelineResponse = { timeline_items?: unknown; updated_at?: string };

interface CacheView {
  committed: TimelineItemCollection;
  visible: TimelineItemCollection;
}

interface PendingChanges {
  changes: TimelineChange[];
  views: Map<QueryKey, CacheView>;
  unsubscribe: () => void;
}

const pendingByClient = new WeakMap<QueryClient, Map<string, PendingChanges>>();

function toItemMap(items: TimelineItemCollection): TimelineItemMap {
  return getTimelineItemMap({ timeline_items: items });
}

function hasItem(items: TimelineItemMap, id: string): boolean {
  return Object.prototype.hasOwnProperty.call(items, id);
}

// Other features can patch the same cache while an edit is pending. Carry their
// changes over from the displayed timeline without committing our own optimism.
function rebaseTimeline(
  committed: TimelineItemCollection,
  visible: TimelineItemCollection,
  current: TimelineItemCollection,
): TimelineItemCollection {
  if (visible === current) return committed;
  const base = toItemMap(committed);
  const before = toItemMap(visible);
  const after = toItemMap(current);
  const next = { ...base };

  for (const id of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (before[id] === after[id]) continue;
    if (!after[id]) {
      delete next[id];
    } else if (!before[id]) {
      next[id] = after[id];
    } else if (base[id]) {
      const oldFields: Record<string, unknown> = { ...before[id] };
      const newFields: Record<string, unknown> = { ...after[id] };
      const updated: Record<string, unknown> = { ...base[id] };
      for (const field of new Set([...Object.keys(oldFields), ...Object.keys(newFields)])) {
        if (oldFields[field] === newFields[field]) continue;
        if (field === 'replies') {
          updated.replies = rebaseTimeline(base[id].replies, before[id].replies, after[id].replies);
        } else if (field in newFields) {
          updated[field] = newFields[field];
        } else {
          delete updated[field];
        }
      }
      next[id] = updated as TimelineItem;
    }
  }
  return next;
}

function itemReplies(item: TimelineItem | null): TimelineItemMap {
  return toItemMap(item?.replies);
}

function insertItem(timeline: TimelineItemMap, item: TimelineItem, parentId: string | null): TimelineItemMap {
  if (!item.id) return timeline;

  const parent = parentId && findTimelineItem(timeline, parentId);
  if (parent && parentId) {
    const replies = itemReplies(parent);
    return hasItem(replies, item.id) ? timeline : updateTimelineItemById(timeline, parentId, {
      replies: { ...replies, [item.id]: item },
    });
  }
  return hasItem(timeline, item.id) ? timeline : { ...timeline, [item.id]: item };
}

function applyChange(timeline: TimelineItemMap, change: TimelineChange): TimelineItemMap {
  switch (change.type) {
    case 'create':
      return change.item ? insertItem(timeline, change.item, change.parentId) : timeline;
    case 'update':
      return updateTimelineItemById(timeline, change.itemId, change.updates);
    case 'delete':
      return removeTimelineItemById(timeline, change.itemId);
  }
}

function reconcileChange(timeline: TimelineItemMap, server: TimelineItemMap, change: TimelineChange): TimelineItemMap {
  if (change.type === 'create') {
    // The server assigns a new ID. A reply may be stored at the root if its parent was removed.
    let committed = Object.values(server).reduce((items, item) => insertItem(items, item, null), timeline);
    if (change.parentId) {
      const parentId = change.parentId;
      const serverReplies = itemReplies(findTimelineItem(server, parentId));
      const cachedReplies = itemReplies(findTimelineItem(committed, parentId));
      for (const [id, item] of Object.entries(serverReplies)) {
        if (!hasItem(cachedReplies, id)) committed = insertItem(committed, item, parentId);
      }
    }
    return committed;
  }

  const serverItem = findTimelineItem(server, change.itemId);
  if (!serverItem) return applyChange(timeline, change);

  const currentItem = findTimelineItem(timeline, change.itemId);
  // Replies and linked timelines are independently populated in each detail view.
  const { source_timeline_items: _linkedTimeline, ...item } = serverItem;
  if (change.type === 'update' && currentItem) {
    return updateTimelineItemById(timeline, change.itemId, { ...item, replies: currentItem.replies });
  }

  return insertItem(removeTimelineItemById(timeline, change.itemId), item, item.parent_id ?? null);
}

export function timelineItemCache(client: QueryClient, entityType: EntityType, entityId: number | null | undefined) {
  const queryKey = entityId == null ? null : getEntityQueryKey(entityType, entityId);
  const mutationKey = ['timeline-item', entityType, entityId] as const;
  // PUT takes a complete item. Execute same-entity mutations in order so a later edit
  // builds its request from committed fields, even while both edits are shown optimistically.
  const scope = { id: JSON.stringify(mutationKey) };
  const queryCache = client.getQueryCache();

  function matchingQueries() {
    return queryKey ? queryCache.findAll({ queryKey }) : [];
  }

  function committedTimeline(key: QueryKey, detail: TimelineDetails, batch?: PendingChanges) {
    const view = batch?.views.get(key);
    return view ? rebaseTimeline(view.committed, view.visible, detail.timeline_items) : detail.timeline_items;
  }

  function publish(batch: PendingChanges, settled?: TimelineChange, response?: TimelineResponse) {
    const server = response && getTimelineItemMap(response);

    for (const query of matchingQueries()) {
      const detail = query.state.data as TimelineDetails | null | undefined;
      if (!detail) continue;

      let committed = committedTimeline(query.queryKey, detail, batch);
      let timeline = toItemMap(committed);
      const responseIsCurrent = response && (
        !response.updated_at || !detail.updated_at || Date.parse(response.updated_at) >= Date.parse(detail.updated_at)
      );

      if (settled && server && responseIsCurrent) {
        const next = reconcileChange(timeline, server, settled);
        if (next !== timeline) committed = next;
        timeline = next;
      }

      const optimistic = batch.changes.reduce(applyChange, timeline);
      const visible = optimistic === timeline ? committed : optimistic;
      const cached = visible === detail.timeline_items
        ? detail
        : client.setQueryData<TimelineDetails>(
          query.queryKey,
          { ...detail, timeline_items: visible },
          { updatedAt: query.state.dataUpdatedAt },
        );

      batch.views.set(query.queryKey, { committed, visible: cached?.timeline_items });
    }
  }

  return {
    mutationKey,
    scope,
    async begin(change: TimelineChange): Promise<TimelineMutationContext> {
      if (!queryKey) return;

      let batches = pendingByClient.get(client);
      if (!batches) {
        batches = new Map();
        pendingByClient.set(client, batches);
      }

      let batch = batches.get(scope.id);
      if (!batch) {
        const next: PendingChanges = {
          changes: [],
          views: new Map(),
          unsubscribe: queryCache.subscribe((event) => {
            if (event.type === 'updated' && event.action.type === 'success' && !event.action.manual &&
                event.query.queryKey[0] === queryKey[0] && event.query.queryKey[1] === queryKey[1]) {
              next.views.delete(event.query.queryKey);
              publish(next);
            }
          }),
        };
        batch = next;
        batches.set(scope.id, batch);
      }

      batch.changes.push(change);
      await client.cancelQueries({ queryKey });
      publish(batch);
      return change;
    },
    readItem(itemId: string) {
      const batch = pendingByClient.get(client)?.get(scope.id);
      let newest: { item: TimelineItem; updatedAt: number; fetchedAt: number } | undefined;
      for (const query of matchingQueries()) {
        const detail = query.state.data as TimelineDetails | null | undefined;
        if (!detail) continue;
        const timeline = toItemMap(committedTimeline(query.queryKey, detail, batch));
        const item = findTimelineItem(timeline, itemId);
        if (!item) continue;
        const updatedAt = Date.parse(detail.updated_at ?? '');
        const fetchedAt = query.state.dataUpdatedAt;
        const entityTimesKnown = newest && Number.isFinite(updatedAt) && Number.isFinite(newest.updatedAt);
        if (!newest || (entityTimesKnown && updatedAt !== newest.updatedAt
          ? updatedAt > newest.updatedAt
          : fetchedAt > newest.fetchedAt)) {
          newest = { item, updatedAt, fetchedAt };
        }
      }
      return newest?.item;
    },
    finish(change: TimelineMutationContext, response?: TimelineResponse) {
      const batches = pendingByClient.get(client);
      const batch = batches?.get(scope.id);
      const index = change && batch ? batch.changes.indexOf(change) : -1;
      if (!queryKey || !batches || !batch || index < 0) return;

      batch.changes.splice(index, 1);
      publish(batch, change, response);
      if (batch.changes.length === 0) {
        batch.unsubscribe();
        batches.delete(scope.id);
        void client.invalidateQueries({ queryKey });
      }
    },
  };
}
