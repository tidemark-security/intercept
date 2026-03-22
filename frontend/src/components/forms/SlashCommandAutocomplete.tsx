"use client";

import React from "react";
import type { SlashCommand } from "@/utils/slashCommands";

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
      className="absolute bottom-full left-0 mb-2 w-full max-w-md shadow-lg z-50 bg-default-background border border-solid border-neutral-border rounded-md"
      role="listbox"
      aria-label="Slash command suggestions"
    >
      <div className="flex flex-col py-1">
        {commands.map((cmd, index) => (
          <button
            key={cmd.command}
            onClick={() => onSelect(cmd)}
            className={`flex items-start gap-3 px-4 py-2 text-left transition-colors ${
              index === selectedIndex
                ? "bg-brand-primary bg-opacity-10"
                : "hover:bg-brand-primary hover:bg-opacity-5"
            }`}
            role="option"
            aria-selected={index === selectedIndex}
            id={`slash-command-${cmd.command}`}
          >
            <div className="flex flex-col items-start gap-0.5">
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
