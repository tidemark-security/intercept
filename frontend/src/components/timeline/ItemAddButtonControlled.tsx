/**
 * Controlled Item Add Button Component
 * 
 * A controlled wrapper that replicates the ItemAddButton UI but with proper
 * separation of concerns:
 * - Flag and Highlight toggles update local state without submitting
 * - Only the main button triggers form submission
 * - Toggle states are passed to the submit handler
 * 
 */

import React, { useState, useCallback } from "react";

import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { Button } from "@/components/buttons/Button";
import { Tooltip } from "@/components/overlays/Tooltip";

import { Flag, Highlighter, Plus } from 'lucide-react';
export interface FlagHighlightState {
  flagged: boolean;
  highlighted: boolean;
}

interface ItemAddButtonControlledProps {
  /** Label for the submit button */
  buttonLabel?: React.ReactNode;
  /** Icon to display in the submit button (default: Plus) */
  buttonIcon?: React.ReactNode;
  /** Called when the main submit button is clicked, with current toggle states */
  onSubmit: (state: FlagHighlightState) => void;
  /** Whether the submit button should be disabled */
  disabled?: boolean;
  /** Whether the form is currently submitting */
  loading?: boolean;
  /** Additional className for the root element */
  className?: string;
  /** Initial flag/highlight state (for edit mode) */
  initialState?: FlagHighlightState;
}

const FLAG_VALUE = "flag";
const HIGHLIGHT_VALUE = "highlight";

/**
 * Individual toggle button with tooltip support
 */
interface ToggleItemProps {
  icon: React.ReactNode;
  tooltip: string;
  isSelected: boolean;
  onClick: () => void;
  disabled?: boolean;
}

function ToggleItem({ icon, tooltip, isSelected, onClick, disabled = false }: ToggleItemProps) {
  return (
    <Tooltip.Provider>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <div
            role="checkbox"
            aria-checked={isSelected}
            aria-disabled={disabled}
            onClick={disabled ? undefined : onClick}
            className={cn(
              "group/toggle flex h-7 w-auto items-center justify-center gap-2 rounded-md px-2 py-1",
              disabled
                ? "cursor-not-allowed opacity-50"
                : "cursor-pointer active:bg-neutral-100",
              isSelected 
                ? "bg-default-background" 
                : disabled ? "" : "hover:bg-neutral-50"
            )}
          >
            <IconWrapper
              className={cn(
                "text-body font-body",
                disabled
                  ? "text-neutral-400"
                  : isSelected 
                    ? "text-brand-primary" 
                    : "text-subtext-color group-hover/toggle:text-default-font group-active/toggle:text-default-font"
              )}
            >
              {icon}
            </IconWrapper>
          </div>
        </Tooltip.Trigger>
        <Tooltip.Content
          side="bottom"
          align="center"
          sideOffset={4}
        >
          {tooltip}
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export function ItemAddButtonControlled({
  buttonLabel,
  buttonIcon = <Plus />,
  onSubmit,
  disabled = false,
  loading = false,
  className,
  initialState,
}: ItemAddButtonControlledProps) {
  // Build initial set from initialState
  const buildInitialSet = () => {
    const set = new Set<string>();
    if (initialState?.flagged) set.add(FLAG_VALUE);
    if (initialState?.highlighted) set.add(HIGHLIGHT_VALUE);
    return set;
  };

  // Track selected toggles as a Set for efficient lookup
  const [selectedToggles, setSelectedToggles] = useState<Set<string>>(buildInitialSet);

  const handleToggle = useCallback((value: string) => {
    setSelectedToggles(prev => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      return next;
    });
  }, []);

  const handleSubmitClick = useCallback(() => {
    onSubmit({
      flagged: selectedToggles.has(FLAG_VALUE),
      highlighted: selectedToggles.has(HIGHLIGHT_VALUE),
    });
    // Only reset toggles after submit if there's no initial state (create mode)
    // In edit mode, we keep the current state visible
    if (!initialState) {
      setSelectedToggles(new Set());
    }
  }, [onSubmit, selectedToggles, initialState]);

  return (
    <div
      className={cn(
        "flex h-full items-end justify-between border border-solid",
        disabled ? "border-neutral-border" : "border-brand-primary",
        className
      )}
    >
      {/* Toggle Group Container */}
      <div className="flex flex-wrap items-center justify-center gap-0.5 overflow-hidden rounded-md bg-default-background px-0.5 py-0.5 h-auto w-auto flex-none self-stretch">
        <ToggleItem
          icon={<Flag />}
          tooltip="Flag Significant"
          isSelected={selectedToggles.has(FLAG_VALUE)}
          onClick={() => handleToggle(FLAG_VALUE)}
          disabled={disabled}
        />
        <ToggleItem
          icon={<Highlighter />}
          tooltip="Highlight Event"
          isSelected={selectedToggles.has(HIGHLIGHT_VALUE)}
          onClick={() => handleToggle(HIGHLIGHT_VALUE)}
          disabled={disabled}
        />
      </div>
      <div className="flex grow items-end justify-between">
        <Button 
          className="w-full" 
          iconRight={buttonIcon}
          onClick={handleSubmitClick}
          disabled={disabled}
          loading={loading}
        >
          {buttonLabel}
        </Button>
      </div>
    </div>
  );
}
