"use client";

import React, { useState } from "react";
import { Dialog } from "@/components/overlays/Dialog";
import { Button } from "@/components/buttons/Button";
import { TextField } from "@/components/forms/TextField";
import { MenuCard } from "@/components/cards/MenuCard";
import { useCases } from "@/hooks/useCases";
import { caseStatusToUIState, priorityToUIPriority } from "@/utils/statusHelpers";
import type { CaseRead } from "@/types/generated/models/CaseRead";


import { Search, X } from 'lucide-react';
interface CaseSelectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectCase: (caseId: number) => void;
  isLinking?: boolean;
}

/**
 * Modal component for selecting an existing case to link an alert to.
 * Displays a searchable list of open cases.
 */
export function CaseSelectorModal({
  isOpen,
  onClose,
  onSelectCase,
  isLinking = false,
}: CaseSelectorModalProps) {
  const [search, setSearch] = useState("");
  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);

  // Fetch open cases (NEW and IN_PROGRESS status)
  const { data: casesData, isLoading } = useCases({
    status: ["NEW", "IN_PROGRESS"],
    search: search || null,
    page: 1,
    size: 20,
  });

  const cases = casesData?.items ?? [];

  const handleSelect = (caseId: number) => {
    setSelectedCaseId(caseId);
  };

  const handleConfirm = () => {
    if (selectedCaseId !== null) {
      onSelectCase(selectedCaseId);
    }
  };

  const handleClose = () => {
    setSearch("");
    setSelectedCaseId(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <Dialog.Content className="w-[600px] max-w-[90vw]">
        {/* Header */}
        <div className="flex w-full items-center justify-between border-b border-solid border-neutral-border px-6 py-4">
          <span className="text-heading-3 font-heading-3 text-default-font">
            Link to Existing Case
          </span>
          <Button
            variant="neutral-tertiary"
            size="small"
            icon={<X />}
            onClick={handleClose}
          />
        </div>

        {/* Search */}
        <div className="w-full px-6 pt-4">
          <TextField
            label=""
            helpText=""
            icon={<Search />}
          >
            <TextField.Input
              placeholder="Search cases..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </TextField>
        </div>

        {/* Case List */}
        <div className="flex w-full flex-col gap-2 px-6 py-4 max-h-[400px] overflow-auto">
          {isLoading ? (
            <div className="flex w-full items-center justify-center py-8">
              <span className="text-body font-body text-subtext-color">
                Loading cases...
              </span>
            </div>
          ) : cases.length === 0 ? (
            <div className="flex w-full items-center justify-center py-8">
              <span className="text-body font-body text-subtext-color">
                No open cases found
              </span>
            </div>
          ) : (
            cases.map((caseItem: CaseRead) => (
              <MenuCard
                key={caseItem.id}
                id={caseItem.human_id}
                title={caseItem.title}
                timestamp={new Date(caseItem.created_at).toLocaleDateString()}
                assignee={caseItem.assignee || "Unassigned"}
                state={caseStatusToUIState(caseItem.status)}
                priority={priorityToUIPriority(caseItem.priority)}
                variant={selectedCaseId === caseItem.id ? "selected" : "default"}
                onClick={() => handleSelect(caseItem.id)}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <div className="flex w-full items-center justify-end gap-2 border-t border-solid border-neutral-border px-6 py-4">
          <Button variant="neutral-secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={selectedCaseId === null || isLinking}
            loading={isLinking}
          >
            Link to Case
          </Button>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
