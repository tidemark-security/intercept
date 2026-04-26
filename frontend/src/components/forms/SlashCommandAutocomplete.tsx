"use client";

import React from "react";
import type { SlashCommand } from "@/utils/slashCommands";
import { cn } from "@/utils/cn";

export interface SlashCommandAutocompleteProps {
  /** List of filtered commands to display */
  commands: SlashCommand[];
  /** Currently selected command index */
  selectedIndex: number;
  /** Callback when command is selected */
  onSelect: (command: SlashCommand) => void;
  /** Callback to close autocomplete */
  onClose: () => void;
}

/**
 * SlashCommandAutocomplete - Dropdown showing filtered slash commands
 * 
 * Features:
 * - Positioned above input (bottom-full)
 * - Keyboard navigation highlighting
 * - Click to select
 * - Shows command label and description
 * 
 * @example
 * ```tsx
 * <SlashCommandAutocomplete
 *   commands={filteredCommands}
 *   selectedIndex={0}
 *   onSelect={handleSelect}
 *   onClose={handleClose}
 * />
 * ```
 */
export function SlashCommandAutocomplete({
  commands,
  selectedIndex,
  onSelect,
  onClose,
}: SlashCommandAutocompleteProps) {
  if (commands.length === 0) {
    return null;
  }

  return (
    <div 
      className="absolute bottom-full left-0 z-[var(--z-popover)] mb-2 flex w-full max-w-md flex-col items-start rounded-md border border-solid border-neutral-200 bg-neutral-50 px-1 py-1 shadow-neutral-200-shadow-medium"
      role="listbox"
      aria-label="Slash command suggestions"
    >
      <div className="flex w-full flex-col items-start">
        {commands.map((cmd, index) => (
          <button
            key={cmd.command}
            onClick={() => onSelect(cmd)}
            className="group/slash-command flex w-full cursor-pointer items-center gap-2 outline-none"
            role="option"
            aria-selected={index === selectedIndex}
            id={`slash-command-${cmd.command}`}
          >
            <div
              className={cn(
                "flex w-full flex-none flex-col items-start gap-0.5 rounded-md px-3 py-2 text-left",
                "hover:bg-neutral-100 focus:bg-neutral-100 active:bg-neutral-50",
                index === selectedIndex && "bg-neutral-100",
              )}
            >
              <span className="text-body-bold font-body-bold text-default-font">
                {cmd.label}
              </span>
              <span className="text-caption font-caption text-subtext-color">
                {cmd.description}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export default SlashCommandAutocomplete;
