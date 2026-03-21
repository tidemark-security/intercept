/**
 * Add Artifact Form Component
 * 
 * Functional form for creating forensic artifact timeline items.
 * Allows documenting file hashes, memory dumps, and other forensic evidence.
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
import type { ForensicArtifactItem } from '@/types/generated/models/ForensicArtifactItem';

import { FileText } from 'lucide-react';
export interface AddArtifactFormProps {
  initialData?: ForensicArtifactItem;
}

export function AddArtifactForm({ initialData }: AddArtifactFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const [isFirstRender, setIsFirstRender] = React.useState(true);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    artifactType: string;
    hash: string;
    hashType: string;
    url: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, ForensicArtifactItem>({
    initialData,
    defaultState: {
      artifactType: '',
      hash: '',
      hashType: '',
      url: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      artifactType: '',  // Not stored in backend model, always empty
      hash: data.hash || '',
      hashType: data.hash_type || '',
      url: data.url || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      hash: state.hash || undefined,
      hash_type: state.hashType || undefined,
      url: state.url || undefined,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
  });

  // Auto-open the select dropdown on first render
  React.useEffect(() => {
    if (isFirstRender) {
      setIsFirstRender(false);
    }
  }, [isFirstRender]);

  return (
    <TimelineFormLayout
      icon={<FileText className="text-neutral-600" />}
      title={editMode ? "Edit Forensic Artifact" : "Add Forensic Artifact"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Artifact" : "Add Artifact"}
      submitDisabled={!formState.hash.trim() && !formState.url.trim() && !formState.description.trim()}
      isSubmitting={isSubmitting}
      useWell={true}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      <Select
        className="h-auto w-full flex-none"
        label="Artifact Type (optional)"
        helpText="Type of forensic evidence"
        placeholder="Select type..."
        value={formState.artifactType}
        onValueChange={(artifactType) => setFormState({ ...formState, artifactType })}
        defaultOpen={!editMode && isFirstRender}
      >
        <Select.Item value="file_hash">File Hash</Select.Item>
        <Select.Item value="memory_dump">Memory Dump</Select.Item>
        <Select.Item value="disk_image">Disk Image</Select.Item>
        <Select.Item value="registry_key">Registry Key</Select.Item>
        <Select.Item value="log_file">Log File</Select.Item>
        <Select.Item value="network_capture">Network Capture (PCAP)</Select.Item>
        <Select.Item value="other">Other</Select.Item>
      </Select>

      <div className="flex w-full gap-4">
        <TextField
          className="h-auto w-full flex-none"
          label="Hash (optional)"
          helpText="File hash or identifier"
        >
          <TextField.Input
            placeholder="e.g., abc123def456..."
            value={formState.hash}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
              setFormState({ ...formState, hash: e.target.value })
            }
          />
        </TextField>

        <Select
          className="h-auto w-40 flex-none"
          label="Hash Type"
          helpText="Hash algorithm"
          placeholder="Select..."
          value={formState.hashType}
          onValueChange={(hashType) => setFormState({ ...formState, hashType })}
        >
          <Select.Item value="md5">MD5</Select.Item>
          <Select.Item value="sha1">SHA-1</Select.Item>
          <Select.Item value="sha256">SHA-256</Select.Item>
          <Select.Item value="sha512">SHA-512</Select.Item>
        </Select>
      </div>

      <TextField
        className="h-auto w-full flex-none"
        label="Evidence Location (optional)"
        helpText="URL or path to evidence file"
      >
        <TextField.Input
          placeholder="https://... or file://..."
          value={formState.url}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, url: e.target.value })
          }
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description (optional)"
        helpText="Additional context about this artifact"
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
        helpText="When this artifact was collected"
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
