"use client";

import React from "react";
import { useTheme } from "@/contexts/ThemeContext";
import { Dialog } from "@/components/overlays/Dialog";
import { Badge } from "@/components/data-display/Badge";
import { Button } from "@/components/buttons/Button";
import { Select } from "@/components/forms/Select";
import { Tag } from "@/components/data-display/Tag";
import { TagsManager } from "@/components/forms/TagsManager";
import { useFeatureFlags } from "@/hooks/useFeatureFlags";
import { cn } from "@/utils/cn";
import { CLOSED_ALERT_STATUS_OPTIONS } from "@/utils/statusLabels";
import { Checkbox } from "@tidemark-security/ux";

import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { ClosedAlertStatus } from "@/utils/statusLabels";
import type { LinkedAlertResolutionUpdate } from "@/hooks/useResolveLinkedAlerts";

import { Bell, Check, CheckCircle, CheckSquare, Copy, HelpCircle, X, XCircle } from "lucide-react";

const CLOSURE_STATUS_OPTIONS: Array<{ value: ClosedAlertStatus; label: string; icon: React.ReactNode }> = [
  { ...CLOSED_ALERT_STATUS_OPTIONS[0], icon: <Check className="h-4 w-4" /> },
  { ...CLOSED_ALERT_STATUS_OPTIONS[1], icon: <CheckCircle className="h-4 w-4" /> },
  { ...CLOSED_ALERT_STATUS_OPTIONS[2], icon: <XCircle className="h-4 w-4" /> },
  { ...CLOSED_ALERT_STATUS_OPTIONS[3], icon: <HelpCircle className="h-4 w-4" /> },
  { ...CLOSED_ALERT_STATUS_OPTIONS[4], icon: <Copy className="h-4 w-4" /> },
];

const SUGGESTED_TAGS = [
  "Resolved",
  "False Positive",
  "True Positive",
  "Escalated",
  "No Action Required",
  "Duplicate",
];

interface LinkedAlertItem {
  id: number;
  human_id: string;
  title: string;
  status: AlertStatus;
}

interface CaseClosureModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  linkedAlerts: LinkedAlertItem[];
  linkedTaskCount: number;
  initialTags: string[];
  isSubmitting?: boolean;
  onConfirm: (payload: {
    alert_updates: LinkedAlertResolutionUpdate[];
    tags: string[];
    note?: string;
  }) => void;
}

function isClosedAlertStatus(status: AlertStatus): status is ClosedAlertStatus {
  return status.startsWith("CLOSED_");
}

function getClosureStatusLabel(status: AlertStatus): string {
  return CLOSURE_STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status;
}

export function CaseClosureModal({
  open,
  onOpenChange,
  linkedAlerts,
  linkedTaskCount,
  initialTags,
  isSubmitting = false,
  onConfirm,
}: CaseClosureModalProps) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";
  const { data: featureFlags } = useFeatureFlags();
  const suggestedTags = featureFlags?.case_closure_recommended_tags?.length
    ? featureFlags.case_closure_recommended_tags
    : SUGGESTED_TAGS;

  const [selectedAlertIds, setSelectedAlertIds] = React.useState<Set<number>>(new Set());
  const [alertStatuses, setAlertStatuses] = React.useState<Partial<Record<number, ClosedAlertStatus>>>({});
  const [bulkStatus, setBulkStatus] = React.useState<ClosedAlertStatus | undefined>();
  const [selectedTags, setSelectedTags] = React.useState<string[]>([]);
  const [analystNote, setAnalystNote] = React.useState("");

  React.useEffect(() => {
    if (!open) {
      return;
    }

    const openAlertIds = linkedAlerts
      .filter((alert) => !isClosedAlertStatus(alert.status))
      .map((alert) => alert.id);

    setSelectedAlertIds(new Set(openAlertIds));
    setAlertStatuses({});
    setBulkStatus(undefined);
    setSelectedTags(initialTags);
    setAnalystNote("");
  }, [open, linkedAlerts, initialTags]);

  const openAlertIds = React.useMemo(
    () => linkedAlerts
      .filter((alert) => !isClosedAlertStatus(alert.status))
      .map((alert) => alert.id),
    [linkedAlerts],
  );
  const selectedOpenCount = openAlertIds.filter((id) => selectedAlertIds.has(id)).length;
  const allOpenSelected = openAlertIds.length > 0 && selectedOpenCount === openAlertIds.length;
  const someOpenSelected = selectedOpenCount > 0 && selectedOpenCount < openAlertIds.length;
  const openAlertsMissingStatus = openAlertIds.some((id) => !alertStatuses[id]);
  const canClose = openAlertIds.length === 0 || !openAlertsMissingStatus;

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      if (prev.includes(tag)) {
        return prev.filter((item) => item !== tag);
      }
      return [...prev, tag];
    });
  };

  const handleSelectAllOpen = (selected: boolean) => {
    setSelectedAlertIds(() => new Set(selected ? openAlertIds : []));
  };

  const handleAlertSelectionChange = (alertId: number, selected: boolean) => {
    setSelectedAlertIds((previous) => {
      const next = new Set(previous);
      if (selected) {
        next.add(alertId);
      } else {
        next.delete(alertId);
      }
      return next;
    });
  };

  const handleBulkStatusChange = (status: ClosedAlertStatus) => {
    setBulkStatus(status);
    setAlertStatuses((previous) => {
      const next = { ...previous };
      openAlertIds.forEach((id) => {
        if (selectedAlertIds.has(id)) {
          next[id] = status;
        }
      });
      return next;
    });
  };

  const handleAlertStatusChange = (alertId: number, status: ClosedAlertStatus) => {
    setAlertStatuses((previous) => ({
      ...previous,
      [alertId]: status,
    }));
  };

  const handleConfirm = () => {
    if (!canClose) {
      return;
    }

    const alertUpdates = openAlertIds.map((id) => ({
      alert_id: id,
      status: alertStatuses[id] as ClosedAlertStatus,
    }));

    onConfirm({
      alert_updates: alertUpdates,
      tags: selectedTags,
      note: analystNote.trim() || undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className="w-[820px] max-w-[95vw] overflow-hidden">
        <div className="flex w-full items-center gap-4 border-b border-solid border-neutral-border px-6 py-4">
          <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
            <span className="text-heading-2 font-heading-2 text-default-font">Close Case</span>
            <span className="text-body font-body text-subtext-color">
              Review and close this case along with linked items
            </span>
          </div>
          <CheckCircle className={cn(isDarkTheme ? "text-brand-primary" : "text-default-font")} />
        </div>

        <div className="flex w-full flex-col items-start gap-6 px-6 pb-6 max-h-[70vh] overflow-auto">
          <div className="flex w-full items-center gap-3">
            <Badge variant="neutral" icon={<Bell />}>
              {linkedAlerts.length} Alerts
            </Badge>
            <Badge variant="neutral" icon={<CheckSquare />}>
              {linkedTaskCount} Tasks
            </Badge>
            <span className="text-caption font-caption text-subtext-color">will be closed with this case</span>
          </div>

          <div className="flex w-full flex-col items-start gap-3">
            <div className="flex w-full flex-wrap items-center gap-3">
              <span className="mr-auto text-caption-bold font-caption-bold text-subtext-color">LINKED ALERTS</span>
            </div>

            <div className="flex max-h-[260px] w-full flex-col items-start gap-2 overflow-auto rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-3">
              {linkedAlerts.length === 0 ? (
                <div className="flex w-full items-center justify-center py-6">
                  <span className="text-caption font-caption text-subtext-color">No linked alerts</span>
                </div>
              ) : (
                <>
                  {openAlertIds.length > 0 ? (
                    <div className="flex w-full items-center gap-3 border-b border-solid border-neutral-border pb-3">
                      <Checkbox
                        aria-label="Select all open linked alerts"
                        checked={allOpenSelected}
                        indeterminate={someOpenSelected}
                        onCheckedChange={handleSelectAllOpen}
                        disabled={isSubmitting}
                        size="small"
                      />
                      <span className="text-caption font-caption text-subtext-color">
                        {selectedOpenCount} of {openAlertIds.length} open alerts selected
                      </span>
                      <div className="ml-auto flex items-center gap-2">
                        <span className="whitespace-nowrap text-caption font-caption text-subtext-color">Set selected to</span>
                        <Select
                          className="w-[280px]"
                          label=""
                          placeholder="Resolution"
                          value={bulkStatus}
                          onValueChange={(value: string) => handleBulkStatusChange(value as ClosedAlertStatus)}
                          disabled={selectedOpenCount === 0 || isSubmitting}
                        >
                          {CLOSURE_STATUS_OPTIONS.map((option) => (
                            <Select.Item key={option.value} value={option.value}>
                              <span className="flex items-center gap-2">
                                {option.icon}
                                <span className="whitespace-nowrap">{option.label}</span>
                              </span>
                            </Select.Item>
                          ))}
                        </Select>
                      </div>
                    </div>
                  ) : null}

                  {linkedAlerts.map((alert, index) => {
                    const isClosed = isClosedAlertStatus(alert.status);
                    const isSelected = selectedAlertIds.has(alert.id);
                    const rowStatus = isClosed ? alert.status : alertStatuses[alert.id];

                    return (
                      <div
                        key={alert.id}
                        className={cn(
                          "flex w-full items-center gap-3",
                          index < linkedAlerts.length - 1 ? "border-b border-solid border-neutral-border pb-3" : "",
                          isClosed ? "opacity-70" : "",
                        )}
                      >
                        <Checkbox
                          aria-label={`Select ${alert.human_id}`}
                          checked={!isClosed && isSelected}
                          onCheckedChange={(checked) => handleAlertSelectionChange(alert.id, checked)}
                          disabled={isClosed || isSubmitting}
                          size="small"
                        />
                        <div className="flex min-w-0 grow shrink basis-0 flex-col items-start gap-1">
                          <span className={cn("block text-caption-bold font-caption-bold", isDarkTheme ? "text-brand-primary" : "text-default-font")}>{alert.human_id}</span>
                          <span className="block truncate text-caption font-caption text-default-font">{alert.title}</span>
                        </div>
                        <div className="w-[280px] shrink-0">
                          {isClosed ? (
                            <div className="flex min-h-8 items-center justify-end text-right text-caption font-caption text-subtext-color">
                              {getClosureStatusLabel(alert.status)}
                            </div>
                          ) : (
                            <Select
                              className="w-full"
                              label=""
                              placeholder="Resolution"
                              value={rowStatus}
                              onValueChange={(value: string) => handleAlertStatusChange(alert.id, value as ClosedAlertStatus)}
                              disabled={isSubmitting}
                            >
                              {CLOSURE_STATUS_OPTIONS.map((option) => (
                                <Select.Item key={option.value} value={option.value}>
                                  <span className="flex items-center gap-2">
                                    {option.icon}
                                    <span className="whitespace-nowrap">{option.label}</span>
                                  </span>
                                </Select.Item>
                              ))}
                            </Select>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          </div>

          <div className="flex w-full flex-col items-start gap-3">
            <span className="text-caption-bold font-caption-bold text-subtext-color">CLOSURE TAGS</span>

            <div className="flex w-full flex-col items-start gap-3 rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-3">
              <div className="flex w-full flex-col items-start gap-2">
                <span className="text-caption font-caption text-subtext-color">Suggested tags</span>
                <div className="flex w-full flex-wrap items-center gap-2">
                  {suggestedTags.map((tag) => (
                    <button key={tag} type="button" className="cursor-pointer" onClick={() => toggleTag(tag)}>
                      <Tag tagText={tag} showDelete={false} searchable={false} />
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex h-px w-full flex-none bg-neutral-border" />

              <div className="flex w-full flex-col items-start gap-2">
                <TagsManager
                  tags={selectedTags}
                  onTagsChange={setSelectedTags}
                  label="Tags"
                  placeholder="Add closure tags"
                />
              </div>
            </div>
          </div>

          <div className="flex w-full flex-col items-start gap-3">
            <span className="text-caption-bold font-caption-bold text-subtext-color">ANALYST NOTE</span>

            <textarea
              className="min-h-32 w-full resize-y rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-2 text-body font-body text-default-font outline-none transition-colors placeholder:text-subtext-color focus:border-brand-primary"
              placeholder="Add optional analyst note"
              value={analystNote}
              onChange={(event) => setAnalystNote(event.target.value)}
              disabled={isSubmitting}
            />
          </div>
        </div>

        <div className="flex w-full items-center justify-between border-t border-solid border-neutral-border px-6 py-4">
          <Button variant="neutral-secondary" icon={<X />} onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button icon={<Check />} onClick={handleConfirm} disabled={!canClose || isSubmitting} loading={isSubmitting}>
            Close Case
          </Button>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
