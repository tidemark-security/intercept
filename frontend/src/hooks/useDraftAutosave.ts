/**
 * Draft Auto-Save Hook
 * 
 * React hook for debounced draft persistence to localStorage.
 * Automatically saves form data after 2 seconds of inactivity.
 * 
 * @example
 * ```tsx
 * const { isSaving, lastSaved, clearDraft } = useDraftAutosave(
 *   alertId,
 *   'note',
 *   { description: noteText, tags: selectedTags }
 * );
 * ```
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { saveDraft, loadDraft, deleteDraft } from "@/utils/draftStorage";
import type { DraftData, TimelineItemType, TimelineItemFormData } from "@/types/drafts";

const AUTOSAVE_DEBOUNCE_MS = 2000; // 2 seconds
const DRAFT_EXPIRATION_HOURS = 24;

export interface UseDraftAutosaveOptions {
  /**
   * Whether to enable auto-save (default: true)
   */
  enabled?: boolean;
  
  /**
   * Custom debounce delay in milliseconds (default: 2000)
   */
  debounceMs?: number;
  
  /**
   * Callback fired when draft is successfully saved
   */
  onSaved?: () => void;
  
  /**
   * Callback fired when draft save fails
   */
  onError?: (error: Error) => void;
}

export interface UseDraftAutosaveReturn {
  /**
   * Whether a save operation is currently queued (debouncing)
   */
  isSaving: boolean;
  
  /**
   * Timestamp of last successful save, or null if never saved
   */
  lastSaved: Date | null;
  
  /**
   * Manually trigger a draft save (bypasses debounce)
   */
  saveDraftNow: () => void;
  
  /**
   * Clear the draft from localStorage
   */
  clearDraft: () => void;
  
  /**
   * Load existing draft from localStorage
   */
  loadExistingDraft: () => DraftData | null;
}

/**
 * Hook for automatic draft persistence with debounced saves
 * 
 * @param alertId - Alert ID the draft belongs to
 * @param itemType - Timeline item type being created
 * @param formData - Current form data to save
 * @param options - Configuration options
 * @returns Draft auto-save state and methods
 */
export function useDraftAutosave(
  alertId: number,
  itemType: TimelineItemType,
  formData: TimelineItemFormData,
  options: UseDraftAutosaveOptions = {}
): UseDraftAutosaveReturn {
  const {
    enabled = true,
    debounceMs = AUTOSAVE_DEBOUNCE_MS,
    onSaved,
    onError,
  } = options;

  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const formDataRef = useRef(formData);

  // Keep formData ref up to date
  useEffect(() => {
    formDataRef.current = formData;
  }, [formData]);

  /**
   * Perform the actual save operation
   */
  const performSave = useCallback(() => {
    if (!enabled || alertId === null || alertId === undefined) {
      return;
    }

    try {
      const now = new Date();
      const expiresAt = new Date(now.getTime() + DRAFT_EXPIRATION_HOURS * 60 * 60 * 1000);

      const draft: DraftData = {
        version: 1,
        alertId,
        entityId: alertId,
        entityType: 'alert',
        itemType,
        createdAt: now.toISOString(),
        expiresAt: expiresAt.toISOString(),
        formData: formDataRef.current,
      };

      saveDraft(draft);
      setLastSaved(now);
      setIsSaving(false);

      if (onSaved) {
        onSaved();
      }
    } catch (error) {
      console.error("Failed to save draft:", error);
      setIsSaving(false);

      if (onError && error instanceof Error) {
        onError(error);
      }
    }
  }, [enabled, alertId, itemType, onSaved, onError]);

  /**
   * Save draft immediately (bypass debounce)
   */
  const saveDraftNow = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    performSave();
  }, [performSave]);

  /**
   * Clear draft from localStorage
   */
  const clearDraft = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    
    if (alertId !== null && alertId !== undefined) {
      deleteDraft(alertId, itemType);
      setLastSaved(null);
      setIsSaving(false);
    }
  }, [alertId, itemType]);

  /**
   * Load existing draft from localStorage
   */
  const loadExistingDraft = useCallback((): DraftData | null => {
    if (alertId === null || alertId === undefined) {
      return null;
    }
    
    return loadDraft(alertId, itemType);
  }, [alertId, itemType]);

  /**
   * Debounced auto-save effect
   */
  useEffect(() => {
    if (!enabled || alertId === null || alertId === undefined) {
      return;
    }

    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Set saving state immediately when form data changes
    setIsSaving(true);

    // Schedule save after debounce period
    debounceTimerRef.current = setTimeout(() => {
      performSave();
    }, debounceMs);

    // Cleanup on unmount or when dependencies change
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [enabled, alertId, itemType, formData, debounceMs, performSave]);

  return {
    isSaving,
    lastSaved,
    saveDraftNow,
    clearDraft,
    loadExistingDraft,
  };
}
