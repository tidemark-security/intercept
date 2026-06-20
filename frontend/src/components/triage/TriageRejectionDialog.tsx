import React, { useState } from 'react';

import { Button } from '@/components/buttons/Button';
import { Dialog } from '@/components/overlays/Dialog';
import { Select } from '@/components/forms/Select';
import { TextArea } from '@/components/forms/TextArea';
import type { RejectionCategory } from '@/types/generated/models/RejectionCategory';

const REJECTION_CATEGORY_OPTIONS: { value: RejectionCategory; label: string }[] = [
  { value: 'INCORRECT_DISPOSITION', label: 'Incorrect Disposition' },
  { value: 'WRONG_SUGGESTED_STATUS', label: 'Wrong Suggested Status' },
  { value: 'WRONG_PRIORITY', label: 'Wrong Priority' },
  { value: 'MISSING_CONTEXT', label: 'Missing Context' },
  { value: 'INCOMPLETE_ANALYSIS', label: 'Incomplete Analysis' },
  { value: 'PREFER_MANUAL_REVIEW', label: 'Prefer Manual Review' },
  { value: 'FALSE_REASONING', label: 'False Reasoning' },
  { value: 'OTHER', label: 'Other' },
];

interface TriageRejectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onReject: (category: RejectionCategory, reason?: string) => void;
}

export function TriageRejectionDialog({
  open,
  onOpenChange,
  onReject,
}: TriageRejectionDialogProps) {
  const [rejectionCategory, setRejectionCategory] = useState<RejectionCategory | ''>('');
  const [rejectionReason, setRejectionReason] = useState('');

  const reset = () => {
    setRejectionCategory('');
    setRejectionReason('');
  };

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      reset();
    }
  };

  const handleRejectConfirm = () => {
    if (rejectionCategory && (rejectionCategory !== 'OTHER' || rejectionReason.trim())) {
      onReject(rejectionCategory, rejectionReason.trim() || undefined);
      handleOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <Dialog.Content className="p-6">
        <div className="flex w-[400px] flex-col gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-heading-3 font-heading-3 text-default-font">
              Reject Recommendation
            </span>
            <span className="text-body font-body text-subtext-color">
              Select the reason for rejecting this AI triage recommendation.
            </span>
          </div>

          <Select
            label="Rejection Category"
            helpText="Required"
            value={rejectionCategory}
            onValueChange={(value) => setRejectionCategory(value as RejectionCategory)}
            placeholder="Select a category..."
          >
            {REJECTION_CATEGORY_OPTIONS.map((option) => (
              <Select.Item key={option.value} value={option.value}>
                {option.label}
              </Select.Item>
            ))}
          </Select>

          <TextArea
            label="Additional Details"
            helpText={rejectionCategory === 'OTHER' ? 'Required for "Other" category' : 'Optional'}
          >
            <TextArea.Input
              placeholder="Provide additional context for the rejection..."
              value={rejectionReason}
              onChange={(event) => setRejectionReason(event.target.value)}
            />
          </TextArea>

          <div className="flex items-center justify-end gap-3">
            <Button
              variant="neutral-secondary"
              size="small"
              onClick={() => handleOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              variant="destructive-primary"
              size="small"
              onClick={handleRejectConfirm}
              disabled={!rejectionCategory || (rejectionCategory === 'OTHER' && !rejectionReason.trim())}
            >
              Reject Recommendation
            </Button>
          </div>
        </div>
      </Dialog.Content>
    </Dialog>
  );
}
