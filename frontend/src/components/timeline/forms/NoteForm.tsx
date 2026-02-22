/**
 * Note Form Component
 * 
 * Rich note creation form for timeline items in the RightDock.
 * Features:
 * - MarkdownInput for rich text editing
 * - DateTimeInput for observed timestamp
 * - Tag management
 * - Flag/Highlight toggles
 * - Submit via ItemAddButton
 * - Automatic draft persistence and parent_id injection via useTimelineForm
 */

import React from "react";
import type { NoteItem } from '@/types/generated/models/NoteItem';
import { MarkdownInput } from "@/components/forms/MarkdownInput";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";

import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";

import { NotebookText } from 'lucide-react';
export interface NoteFormProps {
  /** Initial data to pre-populate when in edit mode */
  initialData?: NoteItem;
}

export function NoteForm({ initialData }: NoteFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    resetCounter,
    alertId,
    caseId,
    initialFlagHighlight,
  } = useTimelineForm<{
    description: string;
    tags: string[];
    timestamp: string;
    flagged: boolean;
    highlighted: boolean;
  }, NoteItem>({
    initialData,
    defaultState: {
      description: "",
      tags: [],
      timestamp: "",
      flagged: false,
      highlighted: false,
    },
    transformInitialData: (data) => ({
      description: data.description || "",
      tags: data.tags || [],
      timestamp: data.timestamp || "",
      flagged: data.flagged || false,
      highlighted: data.highlighted || false,
    }),
    buildPayload: (state) => ({
      description: state.description,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
      flagged: state.flagged,
      highlighted: state.highlighted,
    }),
    validate: (state) => {
      if (!state.description.trim()) {
        return { valid: false, error: "Description is required" };
      }
      return { valid: true };
    },
  });

  const isDraftLoaded = !!initialData; // Simplified - just track if we have initial data

  return (
    <TimelineFormLayout
      icon={<NotebookText className="text-neutral-600" />}
      title={editMode ? "Edit Note" : "Add Note"}
      editMode={editMode}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}  // No clear button in edit mode
      submitLabel={editMode ? "Save Changes" : "Add Note"}
      submitDisabled={!formState.description.trim()}
      isSubmitting={isSubmitting}
      initialFlagHighlight={initialFlagHighlight}
    >
      <MarkdownInput
        key={`markdown-${alertId || caseId}-${isDraftLoaded ? 'loaded' : 'new'}-${resetCounter}`}
        value={formState.description}
        onChange={(value) => {
          const newValue = value || "";
          // Only update if value actually changed to prevent unnecessary re-renders
          if (newValue !== formState.description) {
            setFormState(prev => ({ ...prev, description: newValue }));
          }
        }}
        variant="default"
        className="grow"
        autoFocus={!editMode}
      />

      <DateTimeManager
        value={formState.timestamp}
        onChange={(timestamp) => setFormState(prev => ({ ...prev, timestamp }))}
        label="Timestamp"
        showNowButton={true}
      />

      <TagsManager
        tags={formState.tags}
        onTagsChange={(tags) => setFormState(prev => ({ ...prev, tags }))}
        label="Tags"
        placeholder="Enter tags and press Enter"
      />
    </TimelineFormLayout>
  );
}
