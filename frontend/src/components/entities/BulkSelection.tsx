import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft, ListChecks, X } from "lucide-react";
import { Priority } from "@tidemark-security/ux";
import { Button } from "@/components/buttons/Button";
import { QueueSearchText } from "@/components/search/QueueSearchHighlight";
import type { BulkSelectionItem } from "@/hooks/useEntityBulkActions";
import { bulkEntityLabels } from "@/utils/entityBulkActions";
import { priorityToUIPriority } from "@/utils/statusHelpers";
import { formatEntityStatusLabel, type EntityType } from "@/utils/statusLabels";

interface BulkSelectionControls {
  onBulk: () => void;
  onClear: () => void;
  disabled?: boolean;
}

export function BulkSelectionToolbar({
  count, onBulk, onClear, onReview, disabled, children,
}: BulkSelectionControls & { count: number; onReview?: () => void; children?: ReactNode }) {
  return (
    <div className="flex w-full flex-wrap items-center gap-2 rounded-md border border-solid border-neutral-border bg-default-background px-3 py-2">
      <span className="mr-auto text-body-bold font-body-bold text-default-font">{count} selected</span>
      {onReview && <Button size="small" variant="neutral-secondary" onClick={onReview}>Review selection</Button>}
      <Button size="small" variant="neutral-secondary" icon={<ListChecks />} disabled={disabled} onClick={onBulk}>Bulk</Button>
      {children}
      <Button size="small" variant="neutral-tertiary" icon={<X />} aria-label="Clear selection" disabled={disabled} onClick={onClear} />
    </div>
  );
}

export function BulkSelectionSummary({
  entityType, items, onBulk, onClear, onRemove, onBack, disabled, focusOnOpen,
}: BulkSelectionControls & {
  entityType: EntityType;
  items: readonly BulkSelectionItem[];
  onRemove: (id: number) => void;
  onBack?: () => void;
  focusOnOpen?: boolean;
}) {
  const { plural, Icon } = bulkEntityLabels[entityType];
  const summaryRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (focusOnOpen) summaryRef.current?.focus({ preventScroll: true });
  }, [focusOnOpen]);
  return (
    <section ref={summaryRef} tabIndex={-1} aria-label="Selection summary" className="flex h-full min-h-0 w-full flex-col bg-default-background text-default-font">
      <header className="flex w-full flex-wrap items-center justify-between gap-3 border-b border-solid border-neutral-border px-4 py-4 md:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
          <h2 className="text-heading-2 font-heading-2">{items.length} {plural} selected</h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onBack && <Button size="small" variant="neutral-secondary" icon={<ArrowLeft />} onClick={onBack}>Back to list</Button>}
          {onBack && <Button size="small" variant="neutral-tertiary" onClick={onClear} disabled={disabled}>Clear selection</Button>}
          <Button size="small" variant="neutral-secondary" icon={<ListChecks />} onClick={onBulk} disabled={disabled}>Bulk Action</Button>
        </div>
      </header>
      <ul className="min-h-0 flex-1 divide-y divide-neutral-border overflow-auto px-4 md:px-6">
        {items.map((item) => (
          <li key={item.id} className="flex items-start gap-3 py-3">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-caption font-caption text-subtext-color"><QueueSearchText>{item.human_id}</QueueSearchText></span>
              <span className="break-words text-body-bold font-body-bold"><QueueSearchText>{item.title}</QueueSearchText></span>
              <span className="text-caption font-caption text-subtext-color">
                <QueueSearchText>{formatEntityStatusLabel(entityType, item.status)}</QueueSearchText> · <QueueSearchText>{item.assignee || "Unassigned"}</QueueSearchText>
              </span>
            </div>
            <Priority priority={priorityToUIPriority(item.priority)} size="mini" />
            <Button
              size="small"
              variant="neutral-tertiary"
              icon={<X />}
              aria-label={`Deselect ${item.human_id}`}
              onClick={() => onRemove(item.id)}
              disabled={disabled}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
