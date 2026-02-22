/**
 * Add Registry Form Component
 * 
 * Functional form for creating Windows registry change timeline items.
 * Allows documenting registry modifications with key path, value, and operation type.
 */

import React from "react";

import { Select } from "@/components/forms/Select";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import type { RegistryChangeItem } from '@/types/generated/models/RegistryChangeItem';

import { Database } from 'lucide-react';
export interface AddRegistryFormProps {
  initialData?: RegistryChangeItem;
}

export function AddRegistryForm({ initialData }: AddRegistryFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const keyPathInputRef = React.useRef<HTMLInputElement>(null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    keyPath: string;
    valueName: string;
    valueData: string;
    oldData: string;
    operation: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, RegistryChangeItem>({
    initialData,
    defaultState: {
      keyPath: '',
      valueName: '',
      valueData: '',
      oldData: '',
      operation: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      keyPath: data.registry_key || '',
      valueName: data.registry_value || '',
      valueData: data.new_data || '',
      oldData: data.old_data || '',
      operation: data.operation || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      registry_key: state.keyPath,
      registry_value: state.valueName || undefined,
      new_data: state.valueData || undefined,
      old_data: state.oldData || undefined,
      operation: state.operation || undefined,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
    validate: (state) => {
      if (!state.keyPath.trim()) {
        return { valid: false, error: "Registry key is required" };
      }
      return { valid: true };
    },
  });

  // Auto-focus the key path input when form appears (but not in edit mode)
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        keyPathInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  return (
    <TimelineFormLayout
      icon={<Database className="text-neutral-600" />}
      title={editMode ? "Edit Registry Change" : "Add Registry Change"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Registry Change" : "Add Registry Change"}
      submitDisabled={!formState.keyPath.trim()}
      isSubmitting={isSubmitting}
      useWell={true}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      <TextField
        className="h-auto w-full flex-none"
        label="Registry Key Path"
        helpText="Full path to the registry key"
      >
        <TextField.Input
          ref={keyPathInputRef}
          placeholder="e.g., HKLM\Software\Microsoft\Windows\CurrentVersion\Run"
          value={formState.keyPath}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, keyPath: e.target.value })
          }
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="Value Name (optional)"
        helpText="Name of the registry value"
      >
        <TextField.Input
          placeholder="e.g., MalwareStartup"
          value={formState.valueName}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, valueName: e.target.value })
          }
        />
      </TextField>

      <Select
        className="h-auto w-full flex-none"
        label="Operation (optional)"
        helpText="Type of registry change"
        placeholder="Select operation..."
        value={formState.operation}
        onValueChange={(operation) => setFormState({ ...formState, operation })}
      >
        <Select.Item value="CREATE">Create</Select.Item>
        <Select.Item value="MODIFY">Modify</Select.Item>
        <Select.Item value="DELETE">Delete</Select.Item>
      </Select>

      <TextField
        className="h-auto w-full flex-none"
        label="New Value Data (optional)"
        helpText="New or current value"
      >
        <TextField.Input
          placeholder="e.g., C:\malware.exe"
          value={formState.valueData}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, valueData: e.target.value })
          }
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="Old Value Data (optional)"
        helpText="Previous value (for modifications)"
      >
        <TextField.Input
          placeholder="Previous value"
          value={formState.oldData}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, oldData: e.target.value })
          }
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description (optional)"
        helpText="Additional context about this registry change"
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
        helpText="When this registry change occurred"
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
