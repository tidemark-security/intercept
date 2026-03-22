/**
 * Inline Reply Terminal Component
 * 
 * Wraps QuickTerminal for inline reply mode with additional context and controls.
 * Displays below the timeline item being replied to with visual nesting and
 * provides cancel functionality to exit reply mode.
 */

import React from 'react';
import { QuickTerminal, type EntityType } from '@/components/forms/QuickTerminal';
import type { TimelineItemType } from '@/types/drafts';
import { Button } from '@/components/buttons/Button';


import { X } from 'lucide-react';
export interface InlineReplyTerminalProps {
  /** Entity ID for timeline item creation */
  entityId: number;
  /** Entity type (alert, case, etc.) */
  entityType: EntityType;
  /** ID of parent timeline item being replied to */
  parentItemId: string;
  /** Type of parent item for display context */
  parentItemType?: string;
  /** Number of items in group (if replying to grouped items) */
  groupItemCount?: number;
  /** Nesting depth of reply */
  replyDepth: number;
  /** Callback when slash command is triggered */
  onSlashCommand: (itemType: TimelineItemType) => void;
  /** Callback when plain text note should be submitted */
  onSubmitNote: (text: string) => Promise<void>;
  /** Callback when "Add Note" button clicked */
  onAddNote: () => void;
  /** Callback for dropdown menu item selection */
  onMenuItemSelect: (itemType: TimelineItemType) => void;
  /** Callback when reply mode should be cancelled */
  onCancel: () => void;
  /** Whether terminal is disabled */
  disabled?: boolean;
  /** Whether submission is in progress */
  isSubmitting?: boolean;
  /** Optional: Enable global slash focus shortcut for this terminal */
  enableGlobalSlashFocus?: boolean;
  /** Optional: Suppress global slash focus shortcut for this terminal */
  suppressGlobalSlashFocus?: boolean;
}

export function InlineReplyTerminal({
  entityId,
  entityType,
  parentItemId,
  parentItemType = 'item',
  groupItemCount,
  replyDepth,
  onSlashCommand,
  onSubmitNote,
  onAddNote,
  onMenuItemSelect,
  onCancel,
  disabled,
  isSubmitting,
  enableGlobalSlashFocus = false,
  suppressGlobalSlashFocus = false,
}: InlineReplyTerminalProps) {
  // Generate parent context label
  const parentLabel = groupItemCount && groupItemCount > 1
    ? `group of ${groupItemCount} items`
    : parentItemType;

  // Show depth warning if approaching limit
  const showDepthWarning = replyDepth >= 4;
  const maxDepth = 5;

  return (
    <div className="flex w-full flex-col items-start gap-2 pl-12 pt-2 pb-4 border-l-2 border-solid border-brand-primary">
      {/* Parent context and cancel button */}
      <div className="flex w-full items-center justify-between gap-2 px-2">
        <div className="flex flex-col items-start gap-1">
          <span className="text-caption font-caption text-subtext-color">
            Replying to {parentLabel}
          </span>
          {showDepthWarning && (
            <span className="text-caption font-caption text-error-600">
              Approaching maximum nesting depth ({replyDepth}/{maxDepth})
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-caption font-caption text-subtext-color">
            (Esc to cancel)
          </span>
          <Button
            variant="neutral-secondary"
            size="small"
            icon={<X />}
            onClick={onCancel}
          >
            Cancel
          </Button>
        </div>
      </div>

      {/* Quick Terminal for reply */}
      <div className="flex w-full">
        <QuickTerminal
          entityId={entityId}
          entityType={entityType}
          parentItemId={parentItemId}
          availableItemTypes={[
            'note',
            'attachment',
            'link',
            'observable',
            'system',
            'actor',
            'email',
            'network_traffic',
            'process',
            'registry_change',
            'ttp',
          ]}
          onSlashCommand={onSlashCommand}
          onSubmitNote={onSubmitNote}
          onAddNote={onAddNote}
          onMenuItemSelect={onMenuItemSelect}
          disabled={disabled}
          isSubmitting={isSubmitting}
          enableGlobalSlashFocus={enableGlobalSlashFocus}
          suppressGlobalSlashFocus={suppressGlobalSlashFocus}
        />
      </div>
    </div>
  );
}
