"use client";

import React from "react";
import { useTheme } from "@/contexts/ThemeContext";
import { useSession } from "@/contexts/sessionContext";
import { Dialog } from "@/components/overlays/Dialog";
import { Button } from "@/components/buttons/Button";
import { CaseFormFields } from "@/components/entities/CaseFormFields";
import { useUsers } from "@/hooks/useUsers";
import { cn } from "@/utils/cn";
import type { Priority } from "@/types/generated/models/Priority";
import { CirclePlus, NotebookPen, Plus, X } from "lucide-react";

interface CreateCaseModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  isSubmitting?: boolean;
  submitError?: string | null;
  onSubmit: (payload: {
    title: string;
    description: string;
    priority: Priority;
    assignee: string | null;
    tags: string[];
  }) => void | Promise<void>;
}

export function CreateCaseModal({
  open,
  onOpenChange,
  isSubmitting = false,
  submitError = null,
  onSubmit,
}: CreateCaseModalProps) {
  const { resolvedTheme } = useTheme();
  const { user } = useSession();
  const { data: users = [], isLoading: isLoadingUsers } = useUsers({});
  const isDarkTheme = resolvedTheme === "dark";
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [priority, setPriority] = React.useState<Priority>("MEDIUM");
  const [assignee, setAssignee] = React.useState<string | null>(null);
  const [tags, setTags] = React.useState<string[]>([]);

  React.useEffect(() => {
    if (!open) {
      setTitle("");
      setDescription("");
      setPriority("MEDIUM");
      setAssignee(null);
      setTags([]);
    }
  }, [open]);

  const trimmedTitle = title.trim();
  const trimmedDescription = description.trim();
  const isSubmitDisabled = !trimmedTitle || isSubmitting;

  const handleSubmit = async () => {
    if (isSubmitDisabled) {
      return;
    }

    await onSubmit({
      title: trimmedTitle,
      description: trimmedDescription,
      priority,
      assignee,
      tags,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className="w-[760px] max-w-[95vw] overflow-hidden">
        <div className="flex w-full items-center gap-4 border-b border-solid border-neutral-border px-6 py-4">
          <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
            <span className="text-heading-2 font-heading-2 text-default-font">Create New Case</span>
            <span className="text-body font-body text-subtext-color">
              Create a blank case with the minimum required details
            </span>
          </div>
          <NotebookPen className={cn("h-5 w-5", isDarkTheme ? "text-brand-primary" : "text-default-font")} />
        </div>

        <div className="flex w-full flex-col items-start gap-5 px-6 py-6 max-h-[70vh] overflow-auto">
          <CaseFormFields
            title={title}
            onTitleChange={setTitle}
            description={description}
            onDescriptionChange={setDescription}
            priority={priority}
            onPriorityChange={setPriority}
            assignee={assignee}
            onAssigneeChange={setAssignee}
            tags={tags}
            onTagsChange={setTags}
            users={users}
            isLoadingUsers={isLoadingUsers}
            currentUser={user?.username || null}
            autoFocusDescription={false}
            showRequiredTitleHint
          />

          {submitError ? (
            <div className="w-full rounded-md border border-solid border-error-600 bg-default-background px-3 py-2">
              <span className="text-caption font-caption text-error-700">{submitError}</span>
            </div>
          ) : null}
        </div>

        <div className="flex w-full items-center justify-between border-t border-solid border-neutral-border px-6 py-4">
          <Button
            variant="neutral-secondary"
            icon={<X />}
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            icon={<Plus />}
            onClick={handleSubmit}
            disabled={isSubmitDisabled}
            loading={isSubmitting}
          >
            Create Case
          </Button>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
