/**
 * Add Process Form Component
 * 
 * Functional form for creating process execution timeline items.
 * Allows documenting process activity with name, PID, command line, and parent process.
 */

import React from "react";

import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import type { ProcessItem } from '@/types/generated/models/ProcessItem';

import { Cpu } from 'lucide-react';
export interface AddProcessFormProps {
  initialData?: ProcessItem;
}

export function AddProcessForm({ initialData }: AddProcessFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const processNameInputRef = React.useRef<HTMLInputElement>(null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    processName: string;
    pid: string;
    commandLine: string;
    parentPid: string;
    username: string;
    description: string;
    timestamp: string;
    tags: string[];
  }, ProcessItem>({
    initialData,
    defaultState: {
      processName: '',
      pid: '',
      commandLine: '',
      parentPid: '',
      username: '',
      description: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      processName: data.process_name || '',
      pid: data.process_id?.toString() || '',
      commandLine: data.command_line || '',
      parentPid: data.parent_process_id?.toString() || '',
      username: data.user_account || '',
      description: data.description || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => ({
      process_name: state.processName,
      process_id: state.pid ? parseInt(state.pid, 10) : undefined,
      command_line: state.commandLine || undefined,
      parent_process_id: state.parentPid ? parseInt(state.parentPid, 10) : undefined,
      user_account: state.username || undefined,
      description: state.description || undefined,
      timestamp: state.timestamp || undefined,
      tags: state.tags.length > 0 ? state.tags : undefined,
    }),
    validate: (state) => {
      if (!state.processName.trim()) {
        return { valid: false, error: "Process name is required" };
      }
      return { valid: true };
    },
  });

  // Auto-focus the process name input when form appears (but not in edit mode)
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        processNameInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  return (
    <TimelineFormLayout
      icon={<Cpu className="text-neutral-600" />}
      title={editMode ? "Edit Process" : "Add Process"}
      editMode={editMode}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Update Process" : "Add Process"}
      submitDisabled={!formState.processName.trim()}
      isSubmitting={isSubmitting}
      useWell={true}
      initialFlagHighlight={initialFlagHighlight}
    >
      <TextField
        className="h-auto w-full flex-none"
        label="Process Name"
        helpText="Executable name"
      >
        <TextField.Input
          ref={processNameInputRef}
          placeholder="e.g., chrome.exe, svchost.exe"
          value={formState.processName}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, processName: e.target.value })
          }
        />
      </TextField>

      <div className="flex w-full gap-4">
        <TextField
          className="h-auto w-full flex-none"
          label="Process ID (optional)"
          helpText="PID"
        >
          <TextField.Input
            type="number"
            placeholder="e.g., 1234"
            value={formState.pid}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
              setFormState({ ...formState, pid: e.target.value })
            }
          />
        </TextField>

        <TextField
          className="h-auto w-full flex-none"
          label="Parent PID (optional)"
          helpText="Parent process ID"
        >
          <TextField.Input
            type="number"
            placeholder="e.g., 4567"
            value={formState.parentPid}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
              setFormState({ ...formState, parentPid: e.target.value })
            }
          />
        </TextField>
      </div>

      <TextField
        className="h-auto w-full flex-none"
        label="Command Line (optional)"
        helpText="Full command with arguments"
      >
        <TextField.Input
          placeholder="e.g., chrome.exe --disable-extensions"
          value={formState.commandLine}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, commandLine: e.target.value })
          }
        />
      </TextField>

      <TextField
        className="h-auto w-full flex-none"
        label="User Account (optional)"
        helpText="User context (e.g., SYSTEM, john.doe)"
      >
        <TextField.Input
          placeholder="e.g., SYSTEM"
          value={formState.username}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => 
            setFormState({ ...formState, username: e.target.value })
          }
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Description (optional)"
        helpText="Additional context about this process"
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
        helpText="When this process was observed"
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
