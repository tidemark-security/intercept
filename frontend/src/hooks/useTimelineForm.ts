import { useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { useTimelineFormContext } from '@/contexts/TimelineFormContext';
import { useFormWithDraft } from './useFormWithDraft';
import { useTimelineItemCreate } from './useTimelineItemCreate';
import { useUpdateTimelineItem } from './useUpdateTimelineItem';
import { useToast } from '@/contexts/ToastContext';
import type { TimelineItemType } from '@/types/drafts';
import type { FlagHighlightState } from '@/components/timeline/ItemAddButtonControlled';

/**
 * Validation result for form submission
 */
interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * Configuration for useTimelineForm hook
 */
interface UseTimelineFormOptions<TFormState, TInitialData> {
  /** Initial data for edit mode (from props) */
  initialData?: TInitialData;
  
  /** Default form state for create mode */
  defaultState: TFormState;
  
  /** Transform initial data into form state (for edit mode) */
  transformInitialData: (data: TInitialData) => TFormState;
  
  /** Build mutation payload from form state */
  buildPayload: (state: TFormState) => Record<string, any>;
  
  /** Validate form state before submission (optional) */
  validate?: (state: TFormState) => ValidationResult;
  
  /** Custom success message (optional, defaults to type-based message) */
  successMessage?: string;
  
  /** Custom error message (optional, defaults to type-based message) */
  errorMessage?: string;
}

/**
 * Comprehensive hook that encapsulates ALL common timeline form logic.
 * 
 * This hook combines:
 * - Form state management with draft persistence (useFormWithDraft)
 * - Create/update mutations (useTimelineItemCreate, useUpdateTimelineItem)
 * - Parent ID injection for replies
 * - Toast notifications
 * - Validation
 * - Edit vs create mode handling
 * 
 * Forms using this hook only need to:
 * 1. Define form state structure
 * 2. Render form fields
 * 3. Pass returned handlers to TimelineFormLayout
 * 
 * @example
 * ```tsx
 * const {
 *   formState,
 *   setFormState,
 *   handleSubmit,
 *   handleClear,
 *   isSubmitting,
 *   resetCounter,
 * } = useTimelineForm({
 *   initialData,
 *   defaultState: { title: '', description: '' },
 *   transformInitialData: (data) => ({
 *     title: data.title || '',
 *     description: data.description || '',
 *   }),
 *   buildPayload: (state) => ({
 *     title: state.title,
 *     description: state.description || undefined,
 *   }),
 *   validate: (state) => {
 *     if (!state.title.trim()) {
 *       return { valid: false, error: "Title is required" };
 *     }
 *     return { valid: true };
 *   },
 * });
 * ```
 */
export function useTimelineForm<TFormState extends Record<string, any>, TInitialData extends { id?: string; timestamp?: string; flagged?: boolean; highlighted?: boolean }>({
  initialData,
  defaultState,
  transformInitialData,
  buildPayload,
  validate,
  successMessage,
  errorMessage,
}: UseTimelineFormOptions<TFormState, TInitialData>) {
  const {
    alertId,
    caseId,
    taskId,
    itemType,
    editMode,
    parentItemId,
    onSuccess,
  } = useTimelineFormContext();
  
  const { showToast } = useToast();

  // Determine entity ID and context based on which ID is provided
  // Priority: alertId > caseId > taskId (matches how forms are typically used)
  const entityId = alertId || caseId || taskId;
  const context: 'alert' | 'case' | 'task' = alertId ? 'alert' : caseId ? 'case' : 'task';

  // Form state with draft persistence
  const [formState, setFormState, { clearDraft, handleClear, resetCounter }] = useFormWithDraft<TFormState>(
    entityId || 0, // Fallback to 0 if undefined, though it should be handled by context check
    itemType,
    initialData ? transformInitialData(initialData) : defaultState,
    {
      persistDrafts: !editMode,  // Don't persist drafts in edit mode
      onDraftLoaded: () => {
        if (!editMode) {
          showToast("Draft Restored", "Your previous draft was restored", "brand");
        }
      },
    },
    context
  );

  // Create mutation with parent ID injection for replies
  const createMutation = useTimelineItemCreate(entityId || null, {
    context,
    parentItemId: parentItemId || undefined,
    onSuccess: (data, itemId) => {
      clearDraft();
      handleClear();
      showToast(
        "Success",
        successMessage || `${itemType.charAt(0).toUpperCase() + itemType.slice(1)} created successfully`,
        "success"
      );
      onSuccess?.(itemId);
    },
    onError: (error) => {
      console.error(`Failed to create ${itemType}:`, error);
      showToast(
        "Error",
        errorMessage || `Failed to create ${itemType}. Please try again.`,
        "error"
      );
    },
  });

  // Update mutation
  const updateMutation = useUpdateTimelineItem(entityId, context, {
    onSuccess: () => {
      showToast(
        "Success",
        successMessage || `${itemType.charAt(0).toUpperCase() + itemType.slice(1)} updated successfully`,
        "success"
      );
      onSuccess?.(initialData?.id || undefined);
    },
    onError: (error) => {
      console.error(`Failed to update ${itemType}:`, error);
      showToast(
        "Error",
        errorMessage || `Failed to update ${itemType}. Please try again.`,
        "error"
      );
    },
  });

  /**
   * Submit handler - validates, then creates or updates based on edit mode
   * @param flagHighlightState - Optional flag/highlight state from the submit button toggles
   */
  const handleSubmit = (flagHighlightState?: FlagHighlightState) => {
    // Run validation if provided
    if (validate) {
      const result = validate(formState);
      if (!result.valid) {
        if (result.error) {
          showToast("Validation Error", result.error, "error");
        }
        return;
      }
    }

    // Build the payload
    const payload = buildPayload(formState);

    if (editMode && initialData?.id) {
      // Update existing item - include flag/highlight state if provided
      updateMutation.mutate({
        itemId: initialData.id,
        updates: {
          type: itemType,
          ...payload,
          // Preserve timestamp if not changed
          timestamp: payload.timestamp || initialData.timestamp || new Date().toISOString(),
          // Include flag/highlight state for updates
          ...(flagHighlightState && { flagged: flagHighlightState.flagged }),
          ...(flagHighlightState && { highlighted: flagHighlightState.highlighted }),
        },
      });
    } else {
      // Create new item - include flag/highlight state if provided
      const itemId = uuidv4();
      createMutation.mutate({
        id: itemId,
        type: itemType,
        ...payload,
        // Use provided timestamp or current time
        timestamp: payload.timestamp || new Date().toISOString(),
        // Include flag/highlight state for new items
        ...(flagHighlightState?.flagged && { flagged: true }),
        ...(flagHighlightState?.highlighted && { highlighted: true }),
        // parent_id is automatically injected by useTimelineItemCreate
      });
    }
  };

  // Determine loading state based on mode
  const isSubmitting = editMode ? updateMutation.isPending : createMutation.isPending;

  // Extract initial flag/highlight state for edit mode
  const initialFlagHighlight: FlagHighlightState | undefined = initialData
    ? { flagged: initialData.flagged ?? false, highlighted: initialData.highlighted ?? false }
    : undefined;

  return {
    // Form state
    formState,
    setFormState,
    
    // Handlers
    handleSubmit,
    handleClear,
    
    // Status
    isSubmitting,
    resetCounter,
    
    // Initial flag/highlight state (for edit mode)
    initialFlagHighlight,
    
    // Context values (for convenience)
    alertId,
    caseId,
    taskId,
    itemType,
    editMode,
    parentItemId,
  };
}
