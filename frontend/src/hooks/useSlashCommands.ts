import { useState, useEffect, useCallback } from "react";
import type { TimelineItemType } from "@/types/drafts";
import type { SlashCommand } from "@/utils/slashCommands";
import {
  isSlashCommandInput,
  filterSlashCommands,
  parseSlashCommand,
} from "@/utils/slashCommands";

export interface UseSlashCommandsOptions {
  /** Current input value */
  inputValue: string;
  /** Filter which timeline item types are available */
  availableItemTypes?: TimelineItemType[];
  /** Callback when slash command should be executed */
  onSlashCommand: (itemType: TimelineItemType) => void;
}

export interface UseSlashCommandsReturn {
  /** Filtered commands based on input */
  filteredCommands: SlashCommand[];
  /** Currently selected command index */
  selectedIndex: number;
  /** Whether autocomplete should be visible */
  showAutocomplete: boolean;
  /** Handle keyboard navigation and execution */
  handleKeyDown: (event: React.KeyboardEvent) => boolean;
  /** Select a specific command */
  handleSelect: (command: SlashCommand) => void;
  /** Close autocomplete */
  closeAutocomplete: () => void;
}

/**
 * useSlashCommands - Hook for slash command autocomplete logic
 * 
 * Manages filtering, keyboard navigation, and execution of slash commands.
 * 
 * @example
 * ```tsx
 * const slashCommands = useSlashCommands({
 *   inputValue,
 *   availableItemTypes: ["note", "link", "attachment"],
 *   onSlashCommand: handleSlashCommand,
 * });
 * 
 * // In render:
 * {slashCommands.showAutocomplete && (
 *   <SlashCommandAutocomplete
 *     commands={slashCommands.filteredCommands}
 *     selectedIndex={slashCommands.selectedIndex}
 *     onSelect={slashCommands.handleSelect}
 *   />
 * )}
 * ```
 */
export function useSlashCommands({
  inputValue,
  availableItemTypes,
  onSlashCommand,
}: UseSlashCommandsOptions): UseSlashCommandsReturn {
  const [filteredCommands, setFilteredCommands] = useState<SlashCommand[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [showAutocomplete, setShowAutocomplete] = useState(false);

  // Helper to check if an item type is available
  const isItemTypeAvailable = useCallback(
    (itemType: TimelineItemType) => {
      if (!availableItemTypes) return true;
      return availableItemTypes.includes(itemType);
    },
    [availableItemTypes]
  );

  // Update filtered commands when input changes
  useEffect(() => {
    if (isSlashCommandInput(inputValue)) {
      const filtered = filterSlashCommands(inputValue).filter((cmd) =>
        isItemTypeAvailable(cmd.type)
      );
      setFilteredCommands(filtered);
      setShowAutocomplete(filtered.length > 0);
      setSelectedIndex(0);
    } else {
      setShowAutocomplete(false);
      setFilteredCommands([]);
    }
  }, [inputValue, isItemTypeAvailable]);

  /**
   * Handle keyboard events for navigation and execution
   * Returns true if event was handled (should preventDefault)
   */
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent): boolean => {
      // Only handle when autocomplete is showing
      if (!showAutocomplete) return false;

      if (event.key === "ArrowDown") {
        event.preventDefault();
        setSelectedIndex((prev) =>
          prev < filteredCommands.length - 1 ? prev + 1 : 0
        );
        return true;
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setSelectedIndex((prev) =>
          prev > 0 ? prev - 1 : filteredCommands.length - 1
        );
        return true;
      } else if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (filteredCommands.length > 0) {
          const selectedCommand = filteredCommands[selectedIndex];
          onSlashCommand(selectedCommand.type);
          setShowAutocomplete(false);
        }
        return true;
      }

      return false;
    },
    [showAutocomplete, filteredCommands, selectedIndex, onSlashCommand]
  );

  /**
   * Select a command by clicking
   */
  const handleSelect = useCallback(
    (command: SlashCommand) => {
      onSlashCommand(command.type);
      setShowAutocomplete(false);
    },
    [onSlashCommand]
  );

  /**
   * Close autocomplete
   */
  const closeAutocomplete = useCallback(() => {
    setShowAutocomplete(false);
  }, []);

  return {
    filteredCommands,
    selectedIndex,
    showAutocomplete,
    handleKeyDown,
    handleSelect,
    closeAutocomplete,
  };
}

export default useSlashCommands;
