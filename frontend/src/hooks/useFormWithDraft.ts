/**
 * Generic Form State Hook with Draft Auto-Save
 * 
 * A useState-like hook that automatically persists form state to localStorage
 * and restores it on mount. Works with any form state shape.
 * 
 * @example
 * ```tsx
 * // In NoteForm component
 * const [formState, setFormState, { handleClear, resetCounter, isDraftLoaded }] = useFormWithDraft(
 *   alertId,
 *   'note',
 *   {
 *     description: '',
 *     tags: [],
 *     timestamp: '',
 *     flagged: false,
 *     highlighted: false
 *   }
 * );
 * 
 * // Use like regular state
 * setFormState({ ...formState, description: newValue });
 * 
 * // Pass handleClear directly to TimelineFormLayout
 * <TimelineFormLayout onClear={handleClear} ...>
 *   <MarkdownInput 
 *     key={`markdown-${alertId}-${resetCounter}`}
 *     value={formState.description}
 *     ...
 *   />
 * </TimelineFormLayout>
 * ```
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { saveDraft, loadDraft, deleteDraft } from "@/utils/draftStorage";
import type { DraftData, TimelineItemType } from "@/types/drafts";

const AUTOSAVE_DEBOUNCE_MS = 2000;
const DRAFT_EXPIRATION_HOURS = 24;

export interface UseFormWithDraftOptions {
  /**
   * Whether to enable auto-save (default: true)
   */
  enabled?: boolean;
  
  /**
   * Whether to persist drafts to localStorage (default: true)
   * When false, disables draft persistence (useful for edit mode)
   */
  persistDrafts?: boolean;
  
  /**
   * Custom debounce delay in milliseconds (default: 2000)
   */
  debounceMs?: number;
  
  /**
   * Callback fired when draft is loaded on mount
   */
  onDraftLoaded?: () => void;
  
  /**
   * Callback fired when draft save fails
   */
  onError?: (error: Error) => void;
}

export interface FormDraftControls<T> {
  /**
   * Clear the draft from localStorage (low-level API)
   */
  clearDraft: () => void;
  
  /**
   * Clear draft and reset form to initial state (ready-to-use for onClear prop).
   * Also increments resetCounter to force child components to remount.
   */
  handleClear: () => void;
  
  /**
   * Whether a draft was loaded on mount
   */
  isDraftLoaded: boolean;
  
  /**
   * Whether a save operation is currently queued (debouncing)
   */
  isSaving: boolean;
  
  /**
   * Timestamp of last successful save
   */
  lastSaved: Date | null;
  
  /**
   * Counter that increments on each clear operation.
   * Use this in component keys to force remount: key={`component-${resetCounter}`}
   */
  resetCounter: number;
}

/**
 * Generic form state hook with automatic draft persistence.
 * Works like useState but with localStorage backup.
 * 
 * @param entityId - Entity ID (alert or case) the draft belongs to
 * @param itemType - Timeline item type being created
 * @param initialState - Initial form state (used when no draft exists)
 * @param options - Configuration options
 * @param entityType - Entity type ('alert', 'case', or 'task'), defaults to 'alert'
 * @returns [formState, setFormState, controls]
 */
export function useFormWithDraft<T extends Record<string, any>>(
  entityId: number,
  itemType: TimelineItemType,
  initialState: T,
  options: UseFormWithDraftOptions = {},
  entityType: 'alert' | 'case' | 'task' = 'alert'
): [T, React.Dispatch<React.SetStateAction<T>>, FormDraftControls<T>] {
  const {
    enabled = true,
    persistDrafts = true,
    debounceMs = AUTOSAVE_DEBOUNCE_MS,
    onDraftLoaded,
    onError,
  } = options;
  
  // Determine if drafts should be persisted
  const shouldPersist = enabled && persistDrafts;

  const [formState, setFormState] = useState<T>(initialState);
  const [isDraftLoaded, setIsDraftLoaded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [resetCounter, setResetCounter] = useState(0);
  
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const hasLoadedDraftRef = useRef(false);
  const onDraftLoadedRef = useRef(onDraftLoaded);
  const onErrorRef = useRef(onError);
  const initialStateRef = useRef(initialState);
  const isClearingRef = useRef(false);
  const formStateRef = useRef(formState);
  const previousHadContentRef = useRef(false);

  // Keep callback refs in sync
  useEffect(() => {
    onDraftLoadedRef.current = onDraftLoaded;
    onErrorRef.current = onError;
  }, [onDraftLoaded, onError]);

  // Keep formStateRef in sync with formState
  useEffect(() => {
    formStateRef.current = formState;
  }, [formState]);

  // Update ref when callback changes
  useEffect(() => {
    onDraftLoadedRef.current = onDraftLoaded;
  }, [onDraftLoaded]);

  /**
   * Load draft on mount
   */
  useEffect(() => {
    if (!hasLoadedDraftRef.current && entityId && shouldPersist) {
      try {
        const existingDraft = loadDraft(entityId, itemType, entityType);
        
        if (existingDraft && existingDraft.formData) {
          // Merge draft data with initial state (preserves any new fields in initialState)
          setFormState(prev => ({
            ...prev,
            ...existingDraft.formData
          }));
          setIsDraftLoaded(true);
          hasLoadedDraftRef.current = true;
          
          // Call the callback if provided using ref to avoid dependency issues
          if (onDraftLoadedRef.current) {
            onDraftLoadedRef.current();
          }
        }
      } catch (error) {
        console.error("Failed to load draft:", error);
      }
    }
  }, [entityId, itemType, shouldPersist, entityType]); // Using shouldPersist instead of enabled

  /**
   * Auto-save effect with debouncing
   * Triggers whenever formState changes
   */
  useEffect(() => {
    if (!shouldPersist || !entityId) {
      return;
    }

    // Skip auto-save if we're currently clearing the form
    if (isClearingRef.current) {
      return;
    }

    // Check if form has any meaningful content
    const hasContent = Object.values(formState).some(value => {
      if (Array.isArray(value)) return value.length > 0;
      if (typeof value === 'string') return value.trim().length > 0;
      if (typeof value === 'boolean') return value === true; // Only true is meaningful
      return value != null;
    });

    // Handle transition from content -> empty (user manually deleted everything)
    if (!hasContent && previousHadContentRef.current) {
      deleteDraft(entityId, itemType, entityType);
      setLastSaved(null);
      previousHadContentRef.current = false;
      return;
    }

    // Update the ref for next time
    previousHadContentRef.current = hasContent;

    if (!hasContent) {
      return; // Don't save empty forms
    }

    // Clear existing timer to restart the debounce period
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }

    const timerId = setTimeout(() => {
      // Double-check clearing flag before saving
      if (isClearingRef.current) {
        return;
      }
      
      // Use formStateRef to get the current state, not the closure
      const currentFormState = formStateRef.current;
      
      // Re-check if form has content (it might have been cleared)
      const hasContent = Object.values(currentFormState).some(value => {
        if (Array.isArray(value)) return value.length > 0;
        if (typeof value === 'string') return value.trim().length > 0;
        if (typeof value === 'boolean') return value === true;
        return value != null;
      });
      
      if (!hasContent) {
        return;
      }
      
      try {
        const now = new Date();
        const expiresAt = new Date(now.getTime() + DRAFT_EXPIRATION_HOURS * 60 * 60 * 1000);

        const draft: DraftData = {
          version: 1,
          entityId,
          entityType,
          itemType,
          createdAt: now.toISOString(),
          expiresAt: expiresAt.toISOString(),
          formData: currentFormState,
        };

        saveDraft(draft);
        setLastSaved(now);
      } catch (error) {
        console.error("Failed to save draft:", error);
        
        if (onErrorRef.current && error instanceof Error) {
          onErrorRef.current(error);
        }
      }
    }, debounceMs);
    
    debounceTimerRef.current = timerId;

    // Cleanup: cancel the timer if formState changes again or component unmounts
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
        debounceTimerRef.current = null;
      }
    };
  }, [entityId, itemType, formState, shouldPersist, debounceMs, entityType]);

  /**
   * Clear draft from localStorage (low-level)
   */
  const clearDraft = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    
    if (entityId) {
      deleteDraft(entityId, itemType, entityType);
      setLastSaved(null);
      setIsSaving(false);
    }
  }, [entityId, itemType, entityType]);

  /**
   * Clear draft and reset form to initial state.
   * Ready-to-use handler for TimelineFormLayout's onClear prop.
   */
  const handleClear = useCallback(() => {
    // Set clearing flag to prevent auto-save from triggering
    isClearingRef.current = true;
    
    // Cancel any pending auto-save
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    
    // Delete draft from storage
    clearDraft();
    
    // Reset form state - call setFormState directly to bypass wrapper
    setFormState(initialStateRef.current);
    
    // Reset saved state
    setIsSaving(false);
    setLastSaved(null);
    
    // Increment counter to force child components to remount
    setResetCounter(prev => prev + 1);
    
    // Clear the flag after enough time for all debounce timers to be cleared
    // This needs to be longer than the debounce delay to ensure no saves happen
    setTimeout(() => {
      isClearingRef.current = false;
    }, debounceMs + 500);
  }, [clearDraft, debounceMs]);

  // Wrap setFormState to prevent updates during clear operation
  const wrappedSetFormState = useCallback((
    update: React.SetStateAction<T>
  ) => {
    // Block state updates if we're currently clearing
    if (isClearingRef.current) {
      return;
    }
    setFormState(update);
  }, []);

  return [
    formState,
    wrappedSetFormState,
    {
      clearDraft,
      handleClear,
      isDraftLoaded,
      isSaving,
      lastSaved,
      resetCounter,
    }
  ];
}
