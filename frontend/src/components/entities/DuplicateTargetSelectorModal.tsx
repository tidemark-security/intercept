"use client";

import React, { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import { Button } from "@/components/buttons/Button";
import { MenuCard } from "@/components/cards/MenuCard";
import { TextField } from "@/components/forms/TextField";
import { Dialog } from "@/components/overlays/Dialog";
import { useAlerts } from "@/hooks/useAlerts";
import { useCases } from "@/hooks/useCases";
import type { AlertRead } from "@/types/generated/models/AlertRead";
import type { CaseRead } from "@/types/generated/models/CaseRead";
import {
  alertStatusToUIState,
  caseStatusToUIState,
  priorityToUIPriority,
} from "@/utils/statusHelpers";

export type DuplicateTargetSelection =
  | { type: "case"; id: number }
  | { type: "alert"; id: number };

interface DuplicateTargetSelectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectTarget: (target: DuplicateTargetSelection) => void;
  excludedAlertIds: number[];
  isSubmitting?: boolean;
}

type DuplicateTargetOption =
  | {
      type: "case";
      key: string;
      id: number;
      humanId: string;
      title: string;
      createdAt: string;
      assignee: string;
      status: CaseRead["status"];
      priority: CaseRead["priority"];
    }
  | {
      type: "alert";
      key: string;
      id: number;
      humanId: string;
      title: string;
      createdAt: string;
      assignee: string;
      status: AlertRead["status"];
      priority: AlertRead["priority"];
    };

/**
 * Modal for choosing the canonical case or alert that selected alerts duplicate.
 */
export function DuplicateTargetSelectorModal({
  isOpen,
  onClose,
  onSelectTarget,
  excludedAlertIds,
  isSubmitting = false,
}: DuplicateTargetSelectorModalProps) {
  const [search, setSearch] = useState("");
  const [selectedTarget, setSelectedTarget] = useState<DuplicateTargetSelection | null>(null);

  const { data: casesData, isLoading: isCasesLoading } = useCases({
    status: ["NEW", "IN_PROGRESS"],
    search: search || null,
    page: 1,
    size: 20,
  });

  const { data: alertsData, isLoading: isAlertsLoading } = useAlerts({
    search: search || null,
    page: 1,
    size: 20,
  });

  const excludedAlertIdSet = useMemo(
    () => new Set(excludedAlertIds),
    [excludedAlertIds]
  );

  const options = useMemo<DuplicateTargetOption[]>(() => {
    const caseOptions: DuplicateTargetOption[] = (casesData?.items ?? []).map((caseItem) => ({
      type: "case",
      key: `case-${caseItem.id}`,
      id: caseItem.id,
      humanId: caseItem.human_id,
      title: caseItem.title,
      createdAt: caseItem.created_at,
      assignee: caseItem.assignee || "Unassigned",
      status: caseItem.status,
      priority: caseItem.priority,
    }));

    const alertOptions: DuplicateTargetOption[] = (alertsData?.items ?? [])
      .filter((alert) => !excludedAlertIdSet.has(alert.id))
      .map((alert) => ({
        type: "alert",
        key: `alert-${alert.id}`,
        id: alert.id,
        humanId: alert.human_id,
        title: alert.title,
        createdAt: alert.created_at,
        assignee: alert.assignee || "Unassigned",
        status: alert.status,
        priority: alert.priority,
      }));

    return [...caseOptions, ...alertOptions].sort(
      (left, right) =>
        new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime()
    );
  }, [alertsData?.items, casesData?.items, excludedAlertIdSet]);

  const handleClose = () => {
    setSearch("");
    setSelectedTarget(null);
    onClose();
  };

  const handleConfirm = () => {
    if (selectedTarget !== null) {
      onSelectTarget(selectedTarget);
    }
  };

  const isLoading = isCasesLoading || isAlertsLoading;

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <Dialog.Content className="w-[640px] max-w-[90vw]">
        <div className="flex w-full items-center justify-between border-b border-solid border-neutral-border px-6 py-4">
          <span className="text-heading-3 font-heading-3 text-default-font">
            Close As Duplicate
          </span>
          <Button
            variant="neutral-tertiary"
            size="small"
            icon={<X />}
            onClick={handleClose}
          />
        </div>

        <div className="w-full px-6 pt-4">
          <TextField label="" helpText="" icon={<Search />}>
            <TextField.Input
              placeholder="Search cases and alerts..."
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setSelectedTarget(null);
              }}
            />
          </TextField>
        </div>

        <div className="flex max-h-[420px] w-full flex-col gap-2 overflow-auto px-6 py-4">
          {isLoading ? (
            <div className="flex w-full items-center justify-center py-8">
              <span className="text-body font-body text-subtext-color">
                Loading targets...
              </span>
            </div>
          ) : options.length === 0 ? (
            <div className="flex w-full items-center justify-center py-8">
              <span className="text-body font-body text-subtext-color">
                No cases or alerts found
              </span>
            </div>
          ) : (
            options.map((option) => {
              const isSelected =
                selectedTarget?.type === option.type && selectedTarget.id === option.id;

              return (
                <MenuCard
                  key={option.key}
                  id={`${option.type === "case" ? "Case" : "Alert"} ${option.humanId}`}
                  title={option.title}
                  timestamp={option.createdAt}
                  assignee={option.assignee}
                  state={
                    option.type === "case"
                      ? caseStatusToUIState(option.status)
                      : alertStatusToUIState(option.status)
                  }
                  priority={priorityToUIPriority(option.priority)}
                  variant={isSelected ? "selected" : "default"}
                  onClick={() =>
                    setSelectedTarget(
                      option.type === "case"
                        ? { type: "case", id: option.id }
                        : { type: "alert", id: option.id }
                    )
                  }
                />
              );
            })
          )}
        </div>

        <div className="flex w-full items-center justify-end gap-2 border-t border-solid border-neutral-border px-6 py-4">
          <Button variant="neutral-secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={selectedTarget === null || isSubmitting}
            loading={isSubmitting}
          >
            Close Duplicates
          </Button>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
