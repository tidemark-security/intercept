/**
 * Add Email Form Component
 * 
 * Functional form for creating email timeline items.
 * Based on AddEmailDialog from UI library, enhanced with form state and submission.
 */

import React from "react";

import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import type { EmailItem } from '@/types/generated/models/EmailItem';

import { Mail } from 'lucide-react';
export interface AddEmailFormProps {
  initialData?: EmailItem;
}

export function AddEmailForm({ initialData }: AddEmailFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const senderInputRef = React.useRef<HTMLInputElement>(null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    sender: string;
    recipient: string;
    subject: string;
    messageId: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, EmailItem>({
    initialData,
    defaultState: {
      sender: '',
      recipient: '',
      subject: '',
      messageId: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      sender: data.sender || '',
      recipient: data.recipient || '',
      subject: data.subject || '',
      messageId: data.message_id || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      sender: state.sender,
      recipient: state.recipient,
      subject: state.subject,
      message_id: state.messageId || undefined,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
    validate: (state) => {
      if (!state.sender.trim()) {
        return { valid: false, error: "Sender is required" };
      }
      if (!state.recipient.trim()) {
        return { valid: false, error: "Recipient is required" };
      }
      if (!state.subject.trim()) {
        return { valid: false, error: "Subject is required" };
      }
      return { valid: true };
    },
  });

  // Auto-focus the sender input when form appears (but not in edit mode)
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        senderInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  return (
    <TimelineFormLayout
      icon={<Mail className="text-neutral-600" />}
      title={editMode ? "Edit Email" : "Add Email"}
      editMode={editMode}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Email" : "Add Email"}
      submitDisabled={!formState.sender.trim() || !formState.recipient.trim() || !formState.subject.trim()}
      isSubmitting={isSubmitting}
      useWell={true}
      initialFlagHighlight={initialFlagHighlight}
    >
      <TextField
        className="h-auto w-full flex-none"
        label="Sender"
        helpText="Email address of sender"
      >
        <TextField.Input 
          ref={senderInputRef}
          placeholder="sender@example.com"
          value={formState.sender}
          onChange={(e) => setFormState({ ...formState, sender: e.target.value })}
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="Recipient"
        helpText="Email address of recipient"
      >
        <TextField.Input 
          placeholder="recipient@example.com"
          value={formState.recipient}
          onChange={(e) => setFormState({ ...formState, recipient: e.target.value })}
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="Subject"
        helpText="Email subject line"
      >
        <TextField.Input 
          placeholder="Email subject..."
          value={formState.subject}
          onChange={(e) => setFormState({ ...formState, subject: e.target.value })}
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="Message ID"
        helpText="Unique email message identifier"
      >
        <TextField.Input 
          placeholder="message-id"
          value={formState.messageId}
          onChange={(e) => setFormState({ ...formState, messageId: e.target.value })}
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description"
        helpText="Additional context about this email"
      >
        <TextArea.Input 
          placeholder="Add context about this email..."
          value={formState.description}
          onChange={(e) => setFormState({ ...formState, description: e.target.value })}
        />
      </TextArea>

      <DateTimeManager
        value={formState.timestamp}
        onChange={(timestamp) => setFormState({ ...formState, timestamp })}
        label="Timestamp"
        helpText="When the email was sent"
        placeholder="YYYY-MM-DD HH:MM"
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
