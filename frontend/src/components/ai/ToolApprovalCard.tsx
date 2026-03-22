"use client";

import React from "react";
import { Button } from "@/components/buttons/Button";

import type { ToolApprovalCardProps } from "./types";

import { AlertTriangle } from 'lucide-react';
/**
 * ToolApprovalCard - Displays a tool approval request card
 * 
 * Features:
 * - Warning icon with tool name
 * - Description of what the tool wants to do
 * - Approve and Deny buttons
 */
export function ToolApprovalCard({
  messageId,
  approval,
  onApprove,
  onDeny,
}: ToolApprovalCardProps) {
  return (
    <div className="flex w-full flex-col items-start gap-2 rounded-md border border-solid border-neutral-border bg-neutral-50 px-3 py-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="text-body font-body text-warning-500" />
        <span className="text-body-bold font-body-bold text-default-font">
          Tool Approval Required
        </span>
      </div>
      <span className="w-full text-body font-body text-subtext-color">
        {approval.toolName} wants to {approval.description}
      </span>
      <div className="flex w-full items-center gap-2">
        <Button
          size="small"
          onClick={() => onApprove?.(messageId, approval.id)}
        >
          Approve
        </Button>
        <Button
          variant="neutral-secondary"
          size="small"
          onClick={() => onDeny?.(messageId, approval.id)}
        >
          Deny
        </Button>
      </div>
    </div>
  );
}

export default ToolApprovalCard;
