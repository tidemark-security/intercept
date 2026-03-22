/**
 * Add Link Form Component
 * 
 * Functional form for creating link/URL timeline items.
 * Allows adding external references like VirusTotal reports, documentation, etc.
 */

import React from "react";

import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import type { LinkItem } from "@/types/generated/models/LinkItem";

import { Link } from 'lucide-react';
export interface AddLinkFormProps {
  initialData?: LinkItem;
}

/**
 * Normalize URL by adding https:// scheme if no scheme is present.
 * If a scheme is already present (even uncommon ones), leave it as-is.
 */
const normalizeUrl = (url: string): string => {
  const trimmedUrl = url.trim();
  
  // Check if URL already has a scheme (e.g., http://, https://, ftp://, file://, etc.)
  // A scheme is defined as alphanumeric characters followed by ://
  const hasScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmedUrl);
  
  if (hasScheme) {
    return trimmedUrl;
  }
  
  // No scheme detected, add https://
  return `https://${trimmedUrl}`;
};

export function AddLinkForm({ initialData }: AddLinkFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const urlInputRef = React.useRef<HTMLInputElement>(null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    url: string;
    title: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, LinkItem>({
    initialData,
    defaultState: {
      url: '',
      title: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      url: data.url || '',
      title: '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      url: normalizeUrl(state.url),
      description: state.description || state.title || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
    validate: (state) => {
      if (!state.url.trim()) {
        return { valid: false, error: "URL is required" };
      }
      return { valid: true };
    },
  });

  // Auto-focus the URL input when form appears (but not in edit mode)
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        urlInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  return (
    <TimelineFormLayout
      icon={<Link className="text-neutral-600" />}
      title={editMode ? "Edit Link" : "Add Link"}
      editMode={editMode}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Link" : "Add Link"}
      submitDisabled={!formState.url.trim()}
      isSubmitting={isSubmitting}
      useWell={true}
      initialFlagHighlight={initialFlagHighlight}
    >
      <TextField
        className="h-auto w-full flex-none"
        label="URL"
        helpText="External link or reference (e.g., VirusTotal, documentation)"
      >
        <TextField.Input
          ref={urlInputRef}
          placeholder="https://..."
          value={formState.url}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, url: e.target.value })
          }
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="Title (optional)"
        helpText="Display name for the link"
      >
        <TextField.Input
          placeholder="e.g., VirusTotal Analysis"
          value={formState.title}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, title: e.target.value })
          }
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description (optional)"
        helpText="Additional context or notes about this link"
      >
        <TextArea.Input
          className="h-24 w-full flex-none"
          placeholder="Enter description..."
          value={formState.description}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => 
            setFormState({ ...formState, description: e.target.value })
          }
        />
      </TextArea>

      <DateTimeManager
        value={formState.timestamp}
        onChange={(timestamp) => setFormState({ ...formState, timestamp })}
        label="Timestamp"
        helpText="When this link was relevant"
        showNowButton={true}
      />
      
      <TagsManager
        tags={formState.tags}
        onTagsChange={(tags) => setFormState({ ...formState, tags })}
        label="Tags"
        placeholder="Enter tags and press Enter"
      />
    </TimelineFormLayout>
  );
}
