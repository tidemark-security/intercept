import React from "react";
import { useTimelineFormContext } from "@/contexts/TimelineFormContext";
import { TimelineFormLayout } from "@/components/timeline/TimelineFormLayout";
import { CaseFormFields } from "@/components/entities/CaseFormFields";
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
      ...(type === "case" && initialData.status === "NEW" ? { status: "IN_PROGRESS" as const } : {}),
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
    </TimelineFormLayout>
  );
}
