/**
 * Add Observable Form Component
 * 
 * Functional form for creating observable/IOC timeline items.
 * Based on AddObservableDialog from UI library, enhanced with form state and submission.
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
import { useValidation } from "@/hooks/useValidation";
import type { ObservableItem } from '@/types/generated/models/ObservableItem';
import type { ObservableType } from '@/types/generated/models/ObservableType';

import { Crosshair, Fingerprint } from 'lucide-react';
export interface AddObservableFormProps {
  initialData?: ObservableItem;
}

export function AddObservableForm({ initialData }: AddObservableFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const [isFirstRender, setIsFirstRender] = React.useState(true);
  const [valueError, setValueError] = React.useState<string | null>(null);
  const { validate, rules } = useValidation();
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    observableType: ObservableType | '';
    value: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, ObservableItem>({
    initialData,
    defaultState: {
      observableType: '',
      value: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      observableType: data.observable_type || '',
      value: data.observable_value || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      observable_type: state.observableType as ObservableType,
      observable_value: state.value,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
    validate: (state) => {
      if (!state.observableType) {
        return { valid: false, error: "Observable type is required" };
      }
      if (!state.value.trim()) {
        return { valid: false, error: "Observable value is required" };
      }
      // Validate the observable value format
      const validationResult = validate(`observable.${state.observableType}`, state.value.trim());
      if (!validationResult.valid) {
        return { valid: false, error: validationResult.error || "Invalid observable value" };
      }
      return { valid: true };
    },
  });

  // Auto-open the select dropdown on first render (only in create mode)
  React.useEffect(() => {
    if (isFirstRender) {
      setIsFirstRender(false);
    }
  }, [isFirstRender]);

  // Run initial validation when form loads in edit mode (once rules are available)
  const hasRunInitialValidation = React.useRef(false);
  React.useEffect(() => {
    if (editMode && rules && !hasRunInitialValidation.current && formState.observableType && formState.value.trim()) {
      hasRunInitialValidation.current = true;
      const result = validate(`observable.${formState.observableType}`, formState.value.trim());
      setValueError(result.valid ? null : result.error || "Invalid value");
    }
  }, [editMode, rules, formState.observableType, formState.value, validate]);

  return (
    <TimelineFormLayout
      icon={<Fingerprint className="text-neutral-600" />}
      title={editMode ? "Edit Observable" : "Add Observable"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Save Changes" : "Add Observable"}
      submitDisabled={!formState.observableType || !formState.value.trim() || valueError !== null}
      isSubmitting={isSubmitting}
      useWell={true}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      <Select
        className="h-auto w-full flex-none"
        label="Type"
        placeholder="Select type"
        helpText=""
        icon={<Fingerprint />}
        value={formState.observableType}
        onValueChange={(observableType) => {
          setFormState({ ...formState, observableType: observableType as ObservableType });
          // Re-validate value when type changes (if we have a value)
          if (formState.value.trim()) {
            const result = validate(`observable.${observableType}`, formState.value.trim());
            setValueError(result.valid ? null : result.error || "Invalid value");
          }
        }}
        defaultOpen={!editMode && isFirstRender}
      >
        <Select.Item value="IP">IP Address</Select.Item>
        <Select.Item value="DOMAIN">Domain</Select.Item>
        <Select.Item value="HASH">Hash</Select.Item>
        <Select.Item value="FILENAME">File name</Select.Item>
        <Select.Item value="URL">URL</Select.Item>
        <Select.Item value="EMAIL">Email</Select.Item>
        <Select.Item value="REGISTRY_KEY">Registry Key</Select.Item>
        <Select.Item value="PROCESS_NAME">Process Name</Select.Item>
      </Select>

      <TextField
        className="h-auto w-full flex-none"
        label="Value"
        helpText={valueError || ""}
        icon={<Crosshair />}
        error={valueError !== null}
      >
        <TextField.Input 
          placeholder="Enter observable value"
          value={formState.value}
          onChange={(e) => {
            const newValue = e.target.value;
            setFormState({ ...formState, value: newValue });
            // Validate on every change (if we have a type and non-empty value)
            if (formState.observableType && newValue.trim()) {
              const result = validate(`observable.${formState.observableType}`, newValue.trim());
              setValueError(result.valid ? null : result.error || "Invalid value");
            } else {
              setValueError(null);
            }
          }}
          onBlur={() => {
            // Validate on blur if we have a type and value
            if (formState.observableType && formState.value.trim()) {
              const result = validate(`observable.${formState.observableType}`, formState.value.trim());
              setValueError(result.valid ? null : result.error || "Invalid value");
            }
          }}
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description"
        helpText=""
      >
        <TextArea.Input 
          placeholder="Add context about this observable..."
          value={formState.description}
          onChange={(e) => setFormState({ ...formState, description: e.target.value })}
        />
      </TextArea>

      <DateTimeManager
        value={formState.timestamp}
        onChange={(timestamp) => setFormState({ ...formState, timestamp })}
        label="Timestamp"
        helpText="When was this observable first seen"
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
