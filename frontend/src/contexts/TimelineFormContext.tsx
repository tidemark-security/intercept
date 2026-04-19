import React, { createContext, useContext, ReactNode } from 'react';
import type { TimelineItemType } from '@/types/drafts';

/**
 * Context for timeline item forms - centralizes all common props
 * that were previously passed individually to each form component.
 * 
 * This eliminates prop drilling and ensures consistency across all forms.
 */
interface TimelineFormContextValue {
  /** The alert ID this timeline item belongs to (optional if caseId or taskId is provided) */
  alertId?: number;
  
  /** The case ID this timeline item belongs to (optional if alertId or taskId is provided) */
  caseId?: number;
  
  /** The task ID this timeline item belongs to (optional if alertId or caseId is provided) */
  taskId?: number;
  
  /** The type of timeline item (e.g., 'note', 'task', 'actor', etc.) */
  itemType: TimelineItemType;
  
  /** Whether the form is in edit mode (true) or create mode (false) */
  editMode: boolean;
  
  /** Parent item ID for threaded replies (null for top-level items) */
  parentItemId: string | null;
  
  /** Callback invoked after successful create/update operation */
  onSuccess: (itemId?: string) => void;
  
  /** Callback invoked when user cancels the form */
  onCancel: () => void;
}

const TimelineFormContext = createContext<TimelineFormContextValue | undefined>(undefined);

interface TimelineFormProviderProps {
  alertId?: number;
  caseId?: number;
  taskId?: number;
  itemType: TimelineItemType;
  editMode: boolean;
  parentItemId?: string | null;
  onSuccess: (itemId?: string) => void;
  onCancel: () => void;
  children: ReactNode;
}

/**
 * Provider component for timeline forms.
 * 
 * Wrap form components with this provider to give them access to
 * common props via useTimelineFormContext hook.
 * 
 * @example
 * ```tsx
 * <TimelineFormProvider
 *   alertId={alertId}
 *   itemType="note"
 *   editMode={false}
 *   parentItemId={replyParentId}
 *   onSuccess={handleFormSuccess}
 *   onCancel={handleFormCancel}
 * >
 *   <NoteForm initialData={editData} />
 * </TimelineFormProvider>
 * ```
 */
export function TimelineFormProvider({
  alertId,
  caseId,
  taskId,
  itemType,
  editMode,
  parentItemId = null,
  onSuccess,
  onCancel,
  children,
}: TimelineFormProviderProps) {
  const value: TimelineFormContextValue = {
    alertId,
    caseId,
    taskId,
    itemType,
    editMode,
    parentItemId,
    onSuccess,
    onCancel,
  };

  return (
    <TimelineFormContext.Provider value={value}>
      {children}
    </TimelineFormContext.Provider>
  );
}

/**
 * Hook to access timeline form context values.
 * 
 * Must be called from within a component wrapped by TimelineFormProvider.
 * 
 * @returns Context values: alertId, itemType, editMode, parentItemId, onSuccess, onCancel
 * 
 * @example
 * ```tsx
 * export function NoteForm({ initialData }: NoteFormProps) {
 *   const { alertId, editMode, parentItemId, onSuccess, onCancel } = useTimelineFormContext();
 *   // Use context values instead of props
 * }
 * ```
 */
export function useTimelineFormContext() {
  const context = useContext(TimelineFormContext);
  
  if (context === undefined) {
    throw new Error(
      'useTimelineFormContext must be used within a TimelineFormProvider. ' +
      'Make sure your form component is wrapped with <TimelineFormProvider>.'
    );
  }
  
  return context;
}
