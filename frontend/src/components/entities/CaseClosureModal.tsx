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

import type { AlertStatus } from "@/types/generated/models/AlertStatus";

import { Bell, Check, CheckCircle, Copy, HelpCircle, List, X, XCircle } from "lucide-react";

const CLOSURE_STATUS_OPTIONS: Array<{ value: AlertStatus; label: string; icon: React.ReactNode }> = [
  { value: "CLOSED_TP", label: "True Positive", icon: <Check className="h-4 w-4" /> },
  { value: "CLOSED_BP", label: "True Positive Benign", icon: <CheckCircle className="h-4 w-4" /> },
  { value: "CLOSED_FP", label: "False Positive", icon: <XCircle className="h-4 w-4" /> },
  { value: "CLOSED_UNRESOLVED", label: "Unresolved", icon: <HelpCircle className="h-4 w-4" /> },
  { value: "CLOSED_DUPLICATE", label: "Duplicate", icon: <Copy className="h-4 w-4" /> },
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
    alert_closure_updates: Array<{ alert_id: number; status: AlertStatus }>;
    tags: string[];
  }) => void;
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

  const [statusByAlertId, setStatusByAlertId] = React.useState<Record<number, AlertStatus | undefined>>({});
  const [selectedTags, setSelectedTags] = React.useState<string[]>([]);

  React.useEffect(() => {
    if (!open) {
      return;
    }

    const initialSelections: Record<number, AlertStatus | undefined> = {};
    linkedAlerts.forEach((alert) => {
      if (CLOSURE_STATUS_OPTIONS.some((option) => option.value === alert.status)) {
        initialSelections[alert.id] = alert.status;
      } else {
        initialSelections[alert.id] = undefined;
      }
    });
    setStatusByAlertId(initialSelections);
    setSelectedTags(initialTags);
  }, [open, linkedAlerts, initialTags]);

  const hasAllSelections = linkedAlerts.every((alert) => Boolean(statusByAlertId[alert.id]));

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      if (prev.includes(tag)) {
        return prev.filter((item) => item !== tag);
      }
      return [...prev, tag];
    });
  };

  const handleConfirm = () => {
    if (!hasAllSelections) {
      return;
    }

    const alertClosureUpdates = linkedAlerts
      .map((alert) => {
        const selectedStatus = statusByAlertId[alert.id];
        if (!selectedStatus) {
          return null;
        }
        return {
          alert_id: alert.id,
          status: selectedStatus,
        };
      })
      .filter((value): value is { alert_id: number; status: AlertStatus } => value !== null);

    onConfirm({
      alert_closure_updates: alertClosureUpdates,
      tags: selectedTags,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <Dialog.Content className="w-[720px] max-w-[95vw] overflow-hidden">
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
            <Badge variant="neutral" icon={<List />}>
              {linkedTaskCount} Tasks
            </Badge>
            <span className="text-caption font-caption text-subtext-color">will be closed with this case</span>
          </div>

          <div className="flex w-full flex-col items-start gap-3">
            <span className="text-caption-bold font-caption-bold text-subtext-color">LINKED ALERTS</span>

            <div className="flex max-h-[260px] w-full flex-col items-start gap-2 overflow-auto rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-3">
              {linkedAlerts.length === 0 ? (
                <div className="flex w-full items-center justify-center py-6">
                  <span className="text-caption font-caption text-subtext-color">No linked alerts</span>
                </div>
              ) : (
                linkedAlerts.map((alert, index) => (
                  <div
                    key={alert.id}
                    className={`flex w-full items-center gap-3 ${index < linkedAlerts.length - 1 ? "border-b border-solid border-neutral-border pb-3" : ""}`}
                  >
                    <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
                      <span className={cn("text-caption-bold font-caption-bold", isDarkTheme ? "text-brand-primary" : "text-default-font")}>{alert.human_id}</span>
                      <span className="line-clamp-1 text-caption font-caption text-default-font">{alert.title}</span>
                    </div>

                    <Select
                      className="h-auto w-48 flex-none"
                      label=""
                      placeholder="Closure Code"
                      value={statusByAlertId[alert.id]}
                      onValueChange={(value: string) => {
                        setStatusByAlertId((prev) => ({
                          ...prev,
                          [alert.id]: value as AlertStatus,
                        }));
                      }}
                    >
                      {CLOSURE_STATUS_OPTIONS.map((option) => (
                        <Select.Item key={option.value} value={option.value}>
                          <span className="flex items-center gap-2">
                            {option.icon}
                            <span>{option.label}</span>
                          </span>
                        </Select.Item>
                      ))}
                    </Select>
                  </div>
                ))
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
                      <Tag tagText={tag} showDelete={false} />
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
        </div>

        <div className="flex w-full items-center justify-between border-t border-solid border-neutral-border px-6 py-4">
          <Button variant="neutral-secondary" icon={<X />} onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button icon={<Check />} onClick={handleConfirm} disabled={!hasAllSelections || isSubmitting} loading={isSubmitting}>
            Close Case
          </Button>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
