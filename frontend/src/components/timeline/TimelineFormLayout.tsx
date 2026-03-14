/**
 * Timeline Form Layout Component
 * 
 * Standardized layout wrapper for all timeline item forms in RightDock.
 * Provides consistent:
 * - Header with icon and title
 * - Optional "well" wrapper for form fields
 * - Footer with Cancel and Submit buttons
 * - Flag/Highlight toggle controls for marking items on creation
 */

import React from "react";

import { cn } from "@/utils/cn";
import { Button } from "@/components/buttons/Button";
import { IconButton } from "@/components/buttons/IconButton";
import { ItemAddButtonControlled, type FlagHighlightState } from "./ItemAddButtonControlled";

import { Eraser, Plus, X } from 'lucide-react';
export interface TimelineFormLayoutProps {
  /** Icon component to display in header */
  icon: React.ReactNode;
  /** Form title displayed in header */
  title: string;
  /** Form content/fields */
  children: React.ReactNode;
  /** Callback when submit button is clicked, receives flag/highlight state */
  onSubmit: (flagHighlightState?: FlagHighlightState) => void;
  /** Callback when cancel button is clicked */
  onCancel?: () => void;
  /** Callback when clear button is clicked - should delete draft and reset form */
  onClear?: () => void;
  /** Submit button label */
  submitLabel: string;
  /** Whether submit button should be disabled */
  submitDisabled?: boolean;
  /** Whether form is currently submitting */
  isSubmitting?: boolean;
  /** Whether to wrap children in a "well" container (default: true) */
  useWell?: boolean;
  /** Whether the form is being used in edit mode */
  editMode?: boolean;
  /** Whether to show the flag and highlight toggle options (default: true) */
  showFlagHighlight?: boolean;
  /** Icon to display in the submit button (default: Plus) */
  submitIcon?: React.ReactNode;
  /** Initial flag/highlight state for edit mode */
  initialFlagHighlight?: FlagHighlightState;
  /** Autocomplete mode for the parent form element */
  formAutoComplete?: React.FormHTMLAttributes<HTMLFormElement>["autoComplete"];
}

export function TimelineFormLayout({
  icon,
  title,
  children,
  onSubmit,
  onCancel,
  onClear,
  submitLabel,
  submitDisabled = false,
  isSubmitting = false,
  useWell = true,
  editMode = false,
  showFlagHighlight = true,
  submitIcon = <Plus />,
  initialFlagHighlight,
  formAutoComplete,
}: TimelineFormLayoutProps) {
  const showCancelButton = Boolean(onCancel) && !editMode;
  const showClearButton = Boolean(onClear) && !editMode;

  return (
    <form
      className={cn(
        "flex h-full w-full flex-col items-center gap-6"
      )}
      autoComplete={formAutoComplete}
      onSubmit={(event) => event.preventDefault()}
    >
      {/* Header with Close Button */}
      <div className="flex w-full items-center gap-2">
        {icon}
        <span className="text-heading-3 font-heading-3 text-neutral-800">
          {title}
        </span>
        <div className="ml-auto">
          <IconButton
            icon={<X />}
            onClick={onCancel}
            aria-label="Close"
          />
        </div>
      </div>

      {/* Form Content */}
      {useWell ? (
        <div className="flex w-full grow flex-col items-start border border-solid border-neutral-border bg-default-background gap-6 p-4 overflow-auto">
          {children}
        </div>
      ) : (
        <div className="flex w-full grow flex-col items-start gap-4 overflow-auto">
          {children}
        </div>
      )}

      {/* Footer with Cancel and Submit buttons */}
      <div className="flex w-full flex-col items-center gap-2">
        {(showCancelButton || showClearButton) && (
          <div className="flex w-full items-center gap-2">
            {showCancelButton && (
              <Button
                className="flex-1"
                variant="neutral-secondary"
                icon={<X />}
                onClick={onCancel}
              >
                Cancel
              </Button>
            )}
            {showClearButton && (
              <Button
                className="flex-1"
                variant="destructive-secondary"
                icon={<Eraser />}
                onClick={onClear}
              >
                Clear
              </Button>
            )}
          </div>
        )}

        {showFlagHighlight ? (
          <ItemAddButtonControlled
            buttonLabel={submitLabel}
            buttonIcon={submitIcon}
            onSubmit={onSubmit}
            disabled={submitDisabled || isSubmitting}
            loading={isSubmitting}
            className="w-full"
            initialState={initialFlagHighlight}
          />
        ) : (
          <Button
            className="w-full"
            iconRight={submitIcon}
            onClick={() => onSubmit()}
            disabled={submitDisabled || isSubmitting}
          >
            {submitLabel}
          </Button>
        )}
      </div>
    </form>
  );
}
