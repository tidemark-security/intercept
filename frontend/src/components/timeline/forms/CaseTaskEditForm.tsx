import React from "react";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";

import { MarkdownInput } from "@/components/forms/MarkdownInput";
import { TextField } from "@/components/forms/TextField";
import { TagsManager } from "@/components/forms/TagsManager";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { PrioritySelector } from "@/components/forms/PrioritySelector";
import { useUpdateCase } from "@/hooks/useUpdateCase";
import { useUpdateTask } from "@/hooks/useUpdateTask";
import { useUsers } from "@/hooks/useUsers";
import { useSession } from "@/contexts/sessionContext";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import type { TaskRead } from "@/types/generated/models/TaskRead";
import type { Priority } from "@/types/generated/models/Priority";

import { Check, Edit3 } from 'lucide-react';
export interface CaseTaskEditFormProps {
  initialData: CaseRead | TaskRead;
  type: "case" | "task";
}

export function CaseTaskEditForm({ initialData, type }: CaseTaskEditFormProps) {
  const { onCancel } = useTimelineFormContext();
  const { user } = useSession();
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});
  
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
    priority: initialData.priority || "MEDIUM",
    assignee: initialData.assignee || null,
    tags: initialData.tags || [],
  });

  const handleSubmit = async () => {
    await updateMutation.mutateAsync({
      title: formData.title,
      description: formData.description,
      priority: formData.priority as Priority,
      assignee: formData.assignee,
      tags: formData.tags,
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
      <TextField
        label="Title"
        variant="outline"
        className="w-full"
      >
        <TextField.Input
          value={formData.title}
          onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
          placeholder={`Enter ${type} title`}
        />
      </TextField>

      <PrioritySelector
        className="w-full"
        value={formData.priority}
        onChange={(value) => setFormData(prev => ({ ...prev, priority: value }))}
      />

      <div className="flex w-full flex-col gap-2">
        <span className="text-caption-bold font-caption-bold text-default-font">Assignee</span>
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

      <div className="flex flex-col gap-2 grow w-full">
        <span className="text-caption-bold font-caption-bold text-default-font">Description</span>
        <MarkdownInput
          value={formData.description}
          onChange={(value) => setFormData(prev => ({ ...prev, description: value || "" }))}
          variant="default"
          className="grow w-full"
        />
      </div>

      <TagsManager
        tags={formData.tags}
        onTagsChange={(tags) => setFormData(prev => ({ ...prev, tags }))}
        label="Tags"
        placeholder="Enter tags and press Enter"
      />
    </TimelineFormLayout>
  );
}
