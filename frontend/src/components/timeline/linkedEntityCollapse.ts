import type { TimelineItem } from '@/types/timeline';
import { isAlertItem, isTaskItem } from '@/types/timeline';

export const LINKED_ENTITY_COLLAPSE_STORAGE_KEY = 'intercept.timeline.linkedEntityCollapse.v1';

export type LinkedEntityCollapseState = Record<string, boolean>;

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isLinkedEntityTimelineItem(item: TimelineItem): boolean {
  return item.type === 'alert' || item.type === 'case' || item.type === 'task';
}

export function getLinkedEntityCollapseKey(item: TimelineItem): string | null {
  if (!isLinkedEntityTimelineItem(item)) {
    return null;
  }

  if (isAlertItem(item)) {
    return `alert:${item.alert_id ?? item.id ?? 'unknown'}`;
  }

  if (isTaskItem(item)) {
    const taskItem = item as TimelineItem & { task_id?: number | null; task_human_id?: string | null };
    return `task:${taskItem.task_id ?? taskItem.task_human_id ?? item.id ?? 'unknown'}`;
  }

  const caseItem = item as TimelineItem & { case_id?: number | null };
  return `case:${caseItem.case_id ?? item.id ?? 'unknown'}`;
}

export function loadLinkedEntityCollapseState(storage: Storage | undefined = globalThis.localStorage): LinkedEntityCollapseState {
  if (!storage) {
    return {};
  }

  try {
    const rawValue = storage.getItem(LINKED_ENTITY_COLLAPSE_STORAGE_KEY);
    if (!rawValue) {
      return {};
    }

    const parsed = JSON.parse(rawValue);
    if (!isObjectRecord(parsed)) {
      return {};
    }

    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => typeof value === 'boolean')
    ) as LinkedEntityCollapseState;
  } catch {
    return {};
  }
}

export function saveLinkedEntityCollapseState(
  state: LinkedEntityCollapseState,
  storage: Storage | undefined = globalThis.localStorage,
): void {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(LINKED_ENTITY_COLLAPSE_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // localStorage may be unavailable or full; keep in-memory state usable.
  }
}
