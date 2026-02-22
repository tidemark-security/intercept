/**
 * Add Task Form Component
 * 
 * Functional form for creating task timeline items.
 * Allows adding action items with status, assignee, and due date tracking.
 */

import React from "react";
import type { TaskItem } from '@/types/generated/models/TaskItem';
import type { TaskStatus } from '@/types/generated/models/TaskStatus';
import type { Priority } from '@/types/generated/models/Priority';

import { Select } from "@/components/forms/Select";
import { TextArea } from "@/components/forms/TextArea";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { PrioritySelector } from "@/components/forms/PrioritySelector";
import { useTimelineForm } from "@/hooks/useTimelineForm";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import { useUsers } from "@/hooks/useUsers";
import { useSession } from "@/contexts/sessionContext";

import { CheckSquare } from 'lucide-react';
export interface AddTaskFormProps {
  initialData?: TaskItem;
}

export function AddTaskForm({ initialData }: AddTaskFormProps) {
  const { editMode, onCancel } = useTimelineFormContext();
  const { user } = useSession();
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});
  const titleInputRef = React.useRef<HTMLInputElement>(null);
  
  const {
    formState,
    setFormState,
    handleSubmit,
    handleClear,
    isSubmitting,
    initialFlagHighlight,
  } = useTimelineForm<{
    title: string;
    description: string;
    status: string;
    priority: string;
    assignee: string;
    dueDate: string;
    timestamp: string;
    tags: string[];
  }, TaskItem>({
    initialData,
    defaultState: {
      title: '',
      description: '',
      status: 'TODO',
      priority: 'MEDIUM',
      assignee: '',
      dueDate: '',
      timestamp: '',
      tags: [],
    },
    transformInitialData: (data) => ({
      title: data.title || '',
      description: data.description || '',
      status: data.status || 'TODO',
      priority: data.priority || 'MEDIUM',
      assignee: data.assignee || '',
      dueDate: data.due_date || '',
      timestamp: data.timestamp || '',
      tags: data.tags || [],
    }),
    buildPayload: (state) => {
      const title = state.title.trim();
      const description = state.description.trim();

      return {
        title,
        description: description ? state.description : null,
        status: state.status as TaskStatus,
        priority: state.priority as Priority,
        assignee: state.assignee ? state.assignee : null,
        due_date: state.dueDate ? state.dueDate : null,
        timestamp: state.timestamp || undefined,
        tags: state.tags.length > 0 ? state.tags : undefined,
      };
    },
    validate: (state) => {
      if (!state.title.trim()) {
        return { valid: false, error: "Title is required" };
      }
      return { valid: true };
    },
  });

  // Auto-focus the title input when form appears
  React.useEffect(() => {
    if (!editMode) {
      const timer = setTimeout(() => {
        titleInputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [editMode]);

  return (
    <TimelineFormLayout
      icon={<CheckSquare className="text-neutral-600" />}
      title={editMode ? "Edit Task" : "Add Task"}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      onClear={editMode ? undefined : handleClear}
      submitLabel={editMode ? "Save Changes" : "Add Task"}
      submitDisabled={!formState.title.trim()}
      isSubmitting={isSubmitting}
      useWell={true}
      editMode={editMode}
      initialFlagHighlight={initialFlagHighlight}
    >
      <TextField
        className="h-auto w-full flex-none"
        label="Task Title"
        helpText="Clear, action-oriented summary"
      >
        <TextField.Input
          ref={titleInputRef}
          placeholder="e.g., Review firewall logs"
          value={formState.title}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
            setFormState({ ...formState, title: e.target.value })
          }
        />
      </TextField>

      <TextArea
        className="h-auto w-full flex-none"
        label="Task Details"
        helpText="Optional context; Markdown supported"
      >
        <TextArea.Input
          className="h-24 w-full flex-none"
          placeholder="Add additional notes or instructions"
          value={formState.description}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => 
            setFormState({ ...formState, description: e.target.value })
          }
        />
      </TextArea>

      <Select
        className="h-auto w-full flex-none"
        label="Status"
        helpText="Current task status"
        value={formState.status}
        onValueChange={(status) => setFormState({ ...formState, status })}
      >
        <Select.Item value="TODO">To Do</Select.Item>
        <Select.Item value="IN_PROGRESS">In Progress</Select.Item>
        <Select.Item value="DONE">Done</Select.Item>
      </Select>

      <PrioritySelector
        className="h-auto w-full flex-none"
        label="Priority"
        value={formState.priority as Priority}
        onChange={(priority) => setFormState({ ...formState, priority })}
      />

      <div className="flex w-full flex-col gap-2">
        <span className="text-caption-bold font-caption-bold text-default-font">Assignee (optional)</span>
        <AssigneeSelector
          mode="assign"
          size="medium"
          currentAssignee={formState.assignee || null}
          currentUser={user?.username || null}
          users={users}
          isLoadingUsers={isLoadingUsers}
          onUnassign={() => setFormState({ ...formState, assignee: "" })}
          onAssignToMe={() => setFormState({ ...formState, assignee: user?.username || "" })}
          onAssignToUser={(username) => setFormState({ ...formState, assignee: username })}
          className="w-full"
          dropdownClassName="shadow-none bg-black w-[var(--radix-dropdown-menu-trigger-width)]"
        />
      </div>

      <DateTimeManager
        value={formState.dueDate}
        onChange={(dueDate) => setFormState({ ...formState, dueDate })}
        label="Due Date (optional)"
        helpText="When this task should be completed"
        showNowButton={false}
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
