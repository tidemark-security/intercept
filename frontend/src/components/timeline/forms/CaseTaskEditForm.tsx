import React from "react";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import { CaseFormFields } from "@/components/entities/CaseFormFields";
import { Select } from "@/components/forms/Select";
import { TextField } from "@/components/forms/TextField";
import { MarkdownInput } from "@/components/forms/MarkdownInput";
import { TagsManager } from "@/components/forms/TagsManager";
import { DateTimeManager } from "@/components/forms/DateTimeManager";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { PrioritySelector } from "@/components/forms/PrioritySelector";
import { useUpdateCase } from "@/hooks/useUpdateCase";
import { useUpdateTask } from "@/hooks/useUpdateTask";
import { useUsers } from "@/hooks/useUsers";
import { useSession } from "@/contexts/sessionContext";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import type { Priority } from "@/types/generated/models/Priority";
import type { TaskStatus } from "@/types/generated/models/TaskStatus";

import { Check, Edit3 } from 'lucide-react';
export interface CaseTaskEditFormProps {
  initialData: CaseRead | TaskRead;
  type: "case" | "task";
}

export function CaseTaskEditForm({ initialData, type }: CaseTaskEditFormProps) {
  const { onCancel } = useTimelineFormContext();
  const { user } = useSession();
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});
  const taskInitialData = type === "task" ? initialData as TaskRead : null;
  
  const updateCaseMutation = useUpdateCase(
    type === "case" ? initialData.id : null,
    { onSuccess: () => onCancel() }
  );
  
  const updateTaskMutation = useUpdateTask(
    type === "task" ? initialData.id : null,
    { onSuccess: () => onCancel() }
  );
  
  const updateMutation = type === "case" ? updateCaseMutation : updateTaskMutation;

  const [formData, setFormData] = React.useState({
    title: initialData.title || "",
    description: initialData.description || "",
    status: taskInitialData?.status || "TODO",
    priority: initialData.priority || "MEDIUM",
    assignee: initialData.assignee || null,
    dueDate: taskInitialData?.due_date || "",
    tags: initialData.tags || [],
  });

  const handleSubmit = async () => {
    if (type === "task") {
      await updateTaskMutation.mutateAsync({
        title: formData.title,
        description: formData.description,
        status: formData.status as TaskStatus,
        priority: formData.priority as Priority,
        assignee: formData.assignee,
        due_date: formData.dueDate || null,
        tags: formData.tags,
      });
      return;
    }

    await updateCaseMutation.mutateAsync({
      title: formData.title,
      description: formData.description,
      priority: formData.priority as Priority,
      assignee: formData.assignee,
      tags: formData.tags,
      ...(initialData.status === "NEW" ? { status: "IN_PROGRESS" as const } : {}),
    });
  };

  return (
    <TimelineFormLayout
      icon={<Edit3 className="text-neutral-600" />}
      title={`Edit ${type === "case" ? "Case" : "Task"}`}
      editMode={true}
      onSubmit={handleSubmit}
      onCancel={onCancel}
      submitLabel="Save Changes"
      isSubmitting={updateMutation.isPending}
      showFlagHighlight={false}
      submitIcon={<Check />}
    >
      {type === "task" ? (
        <div className="flex w-full flex-col items-start gap-5">
          <TextField
            className="h-auto w-full flex-none"
            label="Task Title"
            helpText="Clear, action-oriented summary"
          >
            <TextField.Input
              placeholder="e.g., Review firewall logs"
              value={formData.title}
              onChange={(event: React.ChangeEvent<HTMLInputElement>) =>
                setFormData(prev => ({ ...prev, title: event.target.value }))
              }
              maxLength={200}
            />
          </TextField>

          <div className="flex w-full flex-col items-start gap-2">
            <span className="text-caption-bold font-caption-bold text-default-font">Task Details</span>
            <MarkdownInput
              value={formData.description}
              onChange={(value) => setFormData(prev => ({ ...prev, description: value || "" }))}
              className="w-full"
            />
          </div>

          <Select
            className="h-auto w-full flex-none"
            label="Status"
            helpText="Current task status"
            value={formData.status}
            onValueChange={(status) => setFormData(prev => ({ ...prev, status: status as TaskStatus }))}
          >
            <Select.Item value="TODO">To Do</Select.Item>
            <Select.Item value="IN_PROGRESS">In Progress</Select.Item>
            <Select.Item value="DONE">Done</Select.Item>
          </Select>

          <PrioritySelector
            className="h-auto w-full flex-none"
            label="Priority"
            value={formData.priority as Priority}
            onChange={(priority) => setFormData(prev => ({ ...prev, priority }))}
          />

          <div className="flex w-full flex-col gap-2">
            <span className="text-caption-bold font-caption-bold text-default-font">Assignee (optional)</span>
            <AssigneeSelector
              mode="assign"
              size="medium"
              currentAssignee={formData.assignee}
              currentUser={user?.username || null}
              users={users}
              isLoadingUsers={isLoadingUsers}
              onUnassign={() => setFormData(prev => ({ ...prev, assignee: null }))}
              onAssignToMe={() => setFormData(prev => ({ ...prev, assignee: user?.username || null }))}
              onAssignToUser={(username) => setFormData(prev => ({ ...prev, assignee: username }))}
              className="w-full"
              dropdownClassName="shadow-none bg-black w-[var(--radix-dropdown-menu-trigger-width)]"
            />
          </div>

          <DateTimeManager
            value={formData.dueDate}
            onChange={(dueDate) => setFormData(prev => ({ ...prev, dueDate }))}
            label="Due Date (optional)"
            helpText="When this task should be completed"
            showNowButton={false}
          />

          <TagsManager
            tags={formData.tags}
            onTagsChange={(tags) => setFormData(prev => ({ ...prev, tags }))}
            label="Tags"
            placeholder="Enter tags and press Enter"
          />
        </div>
      ) : (
        <CaseFormFields
          title={formData.title}
          onTitleChange={(value) => setFormData(prev => ({ ...prev, title: value }))}
          titleLabel="Title"
          titlePlaceholder={`Enter ${type} title`}
          description={formData.description}
          onDescriptionChange={(value) => setFormData(prev => ({ ...prev, description: value }))}
          priority={formData.priority as Priority}
          onPriorityChange={(value) => setFormData(prev => ({ ...prev, priority: value }))}
          assignee={formData.assignee}
          onAssigneeChange={(value) => setFormData(prev => ({ ...prev, assignee: value }))}
          tags={formData.tags}
          onTagsChange={(value) => setFormData(prev => ({ ...prev, tags: value }))}
          users={users}
          isLoadingUsers={isLoadingUsers}
          currentUser={user?.username || null}
        />
      )}
    </TimelineFormLayout>
  );
}
