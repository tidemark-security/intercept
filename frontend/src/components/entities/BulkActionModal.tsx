import { useId, useState } from "react";
import { Check, CircleCheck, ListChecks, Mail, MailOpen, Square, SquareCheckBig, SquareMinus, X } from "lucide-react";
import { Button } from "@/components/buttons/Button";
import { Badge } from "@/components/data-display/Badge";
import { AlertStatusIcon } from "@/components/entities/AlertStatusIcon";
import { Select } from "@/components/forms/Select";
import { SuggestedTagsField } from "@/components/forms/SuggestedTagsField";
import { Dialog } from "@/components/overlays/Dialog";
import { bulkEntityLabels, type BulkUpdateFields } from "@/utils/entityBulkActions";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { EntityType, StatusOption } from "@/utils/statusLabels";

const unchanged = "unchanged";
const assignToMe = "me";
const caseIcons = { NEW: Mail, IN_PROGRESS: MailOpen, CLOSED: CircleCheck };
const taskIcons = { TODO: Square, IN_PROGRESS: SquareMinus, DONE: SquareCheckBig };

function BulkEntityStatusIcon({ entityType, status }: { entityType: EntityType; status: string }) {
  if (entityType === "alert") return <AlertStatusIcon status={status as AlertStatus} />;
  const Icon = entityType === "case"
    ? caseIcons[status as keyof typeof caseIcons]
    : taskIcons[status as keyof typeof taskIcons];
  return <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />;
}

interface BulkActionModalProps<TStatus extends string> {
  entityType: EntityType;
  count: number;
  statusOptions: readonly StatusOption<TStatus>[];
  users: readonly { username: string }[];
  currentUser: string | null;
  usersLoading: boolean;
  isSubmitting: boolean;
  error?: string;
  onClose: () => void;
  onApply: (fields: BulkUpdateFields<TStatus>) => void;
}

export function BulkActionModal<TStatus extends string>({
  entityType,
  count,
  statusOptions,
  users,
  currentUser,
  usersLoading,
  isSubmitting,
  error,
  onClose,
  onApply,
}: BulkActionModalProps<TStatus>) {
  const [statusChoice, setStatusChoice] = useState<string>(unchanged);
  const [assigneeChoice, setAssigneeChoice] = useState(unchanged);
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const noteId = useId();
  const assignee = assigneeChoice === assignToMe
    ? currentUser ?? undefined
    : assigneeChoice === unchanged ? undefined : assigneeChoice.slice("user:".length);
  const trimmedNote = note.trim();
  const status = statusOptions.find((option) => option.value === statusChoice)?.value;
  const canApply = !!status || !!assignee || tags.length > 0 || !!trimmedNote;
  const { plural, Icon } = bulkEntityLabels[entityType];
  const tooMany = count > 200;

  const handleApply = () => {
    if (!canApply || isSubmitting || tooMany) return;
    onApply({
      status,
      assignee,
      tags: tags.length ? tags : undefined,
      note: trimmedNote || undefined,
    });
  };

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !isSubmitting) onClose(); }}>
      <Dialog.Content className="w-[600px] max-w-[95vw] overflow-hidden">
        <div className="flex w-full items-center justify-between gap-4 border-b border-solid border-neutral-border px-6 py-4">
          <div className="flex flex-col items-start gap-1">
            <Dialog.Title className="text-heading-2 font-heading-2 text-default-font">Bulk Action</Dialog.Title>
            <Dialog.Description className="text-body font-body text-subtext-color">
              Choose what to apply to the selected {plural}.
            </Dialog.Description>
          </div>
          <ListChecks aria-hidden="true" className="shrink-0 text-default-font" />
        </div>

        <fieldset
          disabled={isSubmitting}
          className="flex max-h-[65vh] w-full min-w-0 flex-col items-start gap-5 overflow-auto px-6 py-4"
        >
          <Badge variant="neutral" icon={<Icon />}>{count} selected {plural}</Badge>

          <div className="grid w-full grid-cols-1 gap-4 sm:grid-cols-2">
            <Select
              className="w-full"
              label="Status"
              value={statusChoice}
              disabled={isSubmitting}
              onValueChange={setStatusChoice}
            >
              <Select.Item value={unchanged}>No status selected</Select.Item>
              {statusOptions.map(({ value, label }) => (
                <Select.Item key={value} value={value}>
                  <span className="flex items-center gap-2">
                    <BulkEntityStatusIcon entityType={entityType} status={value} />
                    {label}
                  </span>
                </Select.Item>
              ))}
            </Select>

            <Select
              className="w-full"
              label="Assignee"
              value={assigneeChoice}
              disabled={isSubmitting}
              onValueChange={setAssigneeChoice}
              helpText={usersLoading ? "Loading users…" : undefined}
            >
              <Select.Item value={unchanged}>No assignee selected</Select.Item>
              {currentUser && <Select.Item value={assignToMe}>Assign to me</Select.Item>}
              {users.filter(({ username }) => username !== currentUser).map(({ username }) => (
                <Select.Item key={username} value={`user:${username}`}>{username}</Select.Item>
              ))}
            </Select>
          </div>
          {entityType === "case" && status === "CLOSED" && (
            <p className="text-caption font-caption text-default-font">
              Closing these cases also completes open linked tasks and closes open linked alerts as Unresolved.
            </p>
          )}

          <div className="flex w-full flex-col items-start gap-3">
            <span className="text-caption-bold font-caption-bold text-subtext-color">ADD TAGS</span>
            <SuggestedTagsField tags={tags} onTagsChange={setTags} placeholder={`Add tags to selected ${plural}`} />
          </div>

          <div className="flex w-full flex-col items-start gap-3">
            <label htmlFor={noteId} className="text-caption-bold font-caption-bold text-subtext-color">
              Analyst note
            </label>
            <textarea
              id={noteId}
              className="min-h-32 w-full resize-y rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-2 text-body font-body text-default-font outline-none transition-colors placeholder:text-subtext-color focus:border-brand-primary"
              placeholder={`Add a note to each selected ${entityType}`}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
          {tooMany && <p role="alert" className="text-body font-body text-error-700">Select 200 or fewer {plural} to apply changes.</p>}
          {error && <p role="alert" className="text-body font-body text-error-700">{error}</p>}
        </fieldset>

        <div className="flex w-full items-center justify-between border-t border-solid border-neutral-border px-6 py-4">
          <Button variant="neutral-secondary" icon={<X />} onClick={onClose} disabled={isSubmitting}>Cancel</Button>
          <Button icon={<Check />} onClick={handleApply} disabled={!canApply || isSubmitting || tooMany} loading={isSubmitting}>
            Apply
          </Button>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
