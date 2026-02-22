/**
 * LocalStorage utilities for draft persistence
 */

import type { DraftData, TimelineItemType, RightDockState } from "@/types/drafts";

const DRAFT_KEY_PREFIX = "timeline-draft";
const DOCK_STATE_KEY_PREFIX = "dock-state";
const DRAFT_MAX_SIZE_BYTES = 50 * 1024; // 50KB limit per draft

/**
 * Generate localStorage key for a draft
 */
function getDraftKey(entityId: number, itemType: TimelineItemType, entityType: 'alert' | 'case' | 'task' = 'alert'): string {
  return `${DRAFT_KEY_PREFIX}-${entityType}-${entityId}-${itemType}`;
}

/**
 * Save a draft to localStorage
 * @param draft Draft data to save
 * @throws Error if quota exceeded or serialization fails
 */
export function saveDraft(draft: DraftData): void {
  try {
    const key = getDraftKey(draft.entityId, draft.itemType, draft.entityType);
    const serialized = JSON.stringify(draft);

    // Check size limit
    if (serialized.length > DRAFT_MAX_SIZE_BYTES) {
      console.warn(`Draft exceeds size limit (${serialized.length} bytes)`);
      throw new Error("Draft too large to save");
    }

    localStorage.setItem(key, serialized);
  } catch (error) {
    if (error instanceof Error && error.name === "QuotaExceededError") {
      console.error("localStorage quota exceeded", error);
      throw new Error("Storage quota exceeded - please submit or clear existing drafts");
    }
    console.error("Failed to save draft", error);
    throw error;
  }
}

/**
 * Load a draft from localStorage
 * @param entityId Entity ID (alert, case, or task)
 * @param itemType Timeline item type
 * @param entityType Entity type ('alert', 'case', or 'task')
 * @returns Draft data or null if not found/expired/invalid
 */
export function loadDraft(
  entityId: number,
  itemType: TimelineItemType,
  entityType: 'alert' | 'case' | 'task' = 'alert'
): DraftData | null {
  try {
    // Try new key format first
    const key = getDraftKey(entityId, itemType, entityType);
    let serialized = localStorage.getItem(key);

    // Fallback to old key format for alerts (migration path)
    if (!serialized && entityType === 'alert') {
      const oldKey = `alert-timeline-draft-${entityId}-${itemType}`;
      serialized = localStorage.getItem(oldKey);
    }

    if (!serialized) {
      return null;
    }

    const draft = JSON.parse(serialized) as DraftData;

    // Check if draft is expired
    const now = new Date();
    const expiresAt = new Date(draft.expiresAt);

    if (now > expiresAt) {
      // Delete expired draft
      deleteDraft(entityId, itemType, entityType);
      return null;
    }

    return draft;
  } catch (error) {
    console.error("Failed to load draft", error);
    // Delete corrupted draft
    deleteDraft(entityId, itemType, entityType);
    return null;
  }
}

/**
 * Delete a draft from localStorage
 * @param entityId Entity ID
 * @param itemType Timeline item type
 * @param entityType Entity type
 */
export function deleteDraft(entityId: number, itemType: TimelineItemType, entityType: 'alert' | 'case' | 'task' = 'alert'): void {
  try {
    const key = getDraftKey(entityId, itemType, entityType);
    localStorage.removeItem(key);
    
    // Also try to remove old key format if alert
    if (entityType === 'alert') {
      const oldKey = `alert-timeline-draft-${entityId}-${itemType}`;
      localStorage.removeItem(oldKey);
    }
  } catch (error) {
    console.error("Failed to delete draft", error);
  }
}

/**
 * Clean up expired and orphaned drafts
 * @returns Number of drafts cleaned up
 */
export function cleanupExpiredDrafts(): number {
  let cleanedCount = 0;

  try {
    const now = new Date();
    const keys: string[] = [];

    // Collect all draft keys
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && key.startsWith(DRAFT_KEY_PREFIX)) {
        keys.push(key);
      }
    }

    // Check each draft
    for (const key of keys) {
      try {
        const serialized = localStorage.getItem(key);
        if (!serialized) continue;

        const draft = JSON.parse(serialized) as DraftData;
        const expiresAt = new Date(draft.expiresAt);

        // Delete if expired
        if (now > expiresAt) {
          localStorage.removeItem(key);
          cleanedCount++;
        }
      } catch (error) {
        // Delete corrupted draft
        localStorage.removeItem(key);
        cleanedCount++;
      }
    }
  } catch (error) {
    console.error("Failed to cleanup expired drafts", error);
  }

  return cleanedCount;
}

/**
 * Get all draft keys for debugging
 */
export function getAllDraftKeys(): string[] {
  const keys: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith(DRAFT_KEY_PREFIX)) {
      keys.push(key);
    }
  }
  return keys;
}

// ============================================================================
// Right Dock State Persistence
// ============================================================================

/**
 * Generate localStorage key for dock state
 */
function getDockStateKey(alertId: number): string {
  return `${DOCK_STATE_KEY_PREFIX}-${alertId}`;
}

/**
 * Save Right Dock state for a specific alert
 * @param alertId Alert ID
 * @param state Dock state to save
 */
export function saveDockState(alertId: number, state: RightDockState): void {
  try {
    const key = getDockStateKey(alertId);
    const serialized = JSON.stringify(state);
    localStorage.setItem(key, serialized);
  } catch (error) {
    console.error("Failed to save dock state", error);
  }
}

/**
 * Load Right Dock state for a specific alert
 * @param alertId Alert ID
 * @returns Dock state or null if not found
 */
export function loadDockState(alertId: number): RightDockState | null {
  try {
    const key = getDockStateKey(alertId);
    const serialized = localStorage.getItem(key);

    if (!serialized) {
      return null;
    }

    return JSON.parse(serialized) as RightDockState;
  } catch (error) {
    console.error("Failed to load dock state", error);
    return null;
  }
}

/**
 * Delete dock state for a specific alert
 * @param alertId Alert ID
 */
export function deleteDockState(alertId: number): void {
  try {
    const key = getDockStateKey(alertId);
    localStorage.removeItem(key);
  } catch (error) {
    console.error("Failed to delete dock state", error);
  }
}
