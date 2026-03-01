import React from "react";
import { TextField } from "@/components/forms/TextField";
import { MarkdownInput } from "@/components/forms/MarkdownInput";
import { TagsManager } from "@/components/forms/TagsManager";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { PrioritySelector } from "@/components/forms/PrioritySelector";
import type { Priority } from "@/types/generated/models/Priority";
import type { app__api__routes__admin_auth__UserSummary } from "@/types/generated/models/app__api__routes__admin_auth__UserSummary";

interface CaseFormFieldsProps {
  title: string;
  onTitleChange: (value: string) => void;
  titleLabel?: string;
  titlePlaceholder?: string;
  description: string;
  onDescriptionChange: (value: string) => void;
  priority: Priority;
  onPriorityChange: (value: Priority) => void;
  assignee: string | null;
  onAssigneeChange: (value: string | null) => void;
  tags: string[];
  onTagsChange: (tags: string[]) => void;
  users: app__api__routes__admin_auth__UserSummary[];
  isLoadingUsers?: boolean;
  currentUser: string | null;
  autoFocusDescription?: boolean;
  showRequiredTitleHint?: boolean;
  className?: string;
}

export function CaseFormFields({
  title,
  onTitleChange,
  titleLabel = "Case Title",
  titlePlaceholder = "e.g., Suspicious network activity detected",
  description,
  onDescriptionChange,
  priority,
  onPriorityChange,
  assignee,
  onAssigneeChange,
  tags,
  onTagsChange,
  users,
  isLoadingUsers = false,
  currentUser,
  autoFocusDescription = false,
  showRequiredTitleHint = false,
  className = "",
}: CaseFormFieldsProps) {
  return (
    <div className={`flex w-full flex-col items-start gap-5 ${className}`}>
      <TextField className="h-auto w-full flex-none" label={titleLabel} helpText={showRequiredTitleHint ? "Required" : ""}>
        <TextField.Input
          placeholder={titlePlaceholder}
          value={title}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => onTitleChange(event.target.value)}
          maxLength={200}
        />
      </TextField>

      <PrioritySelector
        className="w-full"
        value={priority}
        onChange={onPriorityChange}
      />

      <div className="flex w-full flex-col gap-2">
        <span className="text-caption-bold font-caption-bold text-default-font">Assignee</span>
        <AssigneeSelector
          mode="assign"
          size="medium"
          currentAssignee={assignee}
          currentUser={currentUser}
          users={users}
          isLoadingUsers={isLoadingUsers}
          onUnassign={() => onAssigneeChange(null)}
          onAssignToMe={() => onAssigneeChange(currentUser)}
          onAssignToUser={(username) => onAssigneeChange(username)}
          className="w-full"
          dropdownClassName="shadow-none bg-black w-[var(--radix-dropdown-menu-trigger-width)]"
        />
      </div>

      <div className="flex w-full flex-col items-start gap-2">
        <span className="text-caption-bold font-caption-bold text-default-font">Description</span>
        <MarkdownInput
          value={description}
          onChange={(value) => onDescriptionChange(value || "")}
          className="w-full"
          autoFocus={autoFocusDescription}
        />
      </div>

      <TagsManager
        tags={tags}
        onTagsChange={onTagsChange}
        label="Tags"
        placeholder="Enter tags and press Enter"
      />
    </div>
  );
}
