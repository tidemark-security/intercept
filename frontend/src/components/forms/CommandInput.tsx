"use client";

import React, { useState, useCallback, useEffect, useRef, forwardRef, useImperativeHandle } from "react";
import type { TimelineItemType } from "@/types/drafts";
import { useSlashCommands } from "@/hooks/useSlashCommands";
import { SlashCommandAutocomplete } from "./SlashCommandAutocomplete";
import { isSlashCommandInput, parseSlashCommand } from "@/utils/slashCommands";

export interface CommandInputProps {
  /** Current value */
  value: string;
  /** Callback when value changes */
  onChange: (value: string) => void;
  /** Callback when user submits (Enter key). Return false to keep input unchanged. */
  onSubmit: (value: string) => void | boolean | Promise<void | boolean>;
  /** Placeholder text */
  placeholder?: string;
  /** Whether input is disabled */
  disabled?: boolean;
  /** Whether submission is in progress */
  isLoading?: boolean;
  
  // Multi-line configuration
  /** Enable multi-line textarea (default: true) */
  multiline?: boolean;
  /** Minimum number of lines (default: 1) */
  minLines?: number;
  /** Maximum number of lines (default: 5) */
  maxLines?: number;
  /** Float above content when expanded (default: true) */
  floatOnExpand?: boolean;
  
  // Slash commands (optional)
  /** Enable slash command autocomplete (default: false) */
  enableSlashCommands?: boolean;
  /** Filter which timeline item types are available */
  availableCommands?: TimelineItemType[];
  /** Callback when slash command should be executed */
  onSlashCommand?: (itemType: TimelineItemType) => void;
  
  // Icons & actions (slot-based)
  /** Left icon element */
  leftIcon?: React.ReactNode;
  /** Right action elements (buttons, etc) */
  rightActions?: React.ReactNode;
  
  // Keyboard behavior
  /** Callback when Escape key pressed */
  onEscape?: () => void;
  /** Submit on Enter key (default: true) */
  submitOnEnter?: boolean;
  /** Allow Shift+Enter for new line (default: true for multiline) */
  allowShiftEnter?: boolean;
  
  // Styling
  /** Additional CSS classes */
  className?: string;
  /** Auto-focus on mount */
  autoFocus?: boolean;
  /** Enable global slash/ctrl-slash shortcut to focus this input (default: false) */
  enableGlobalSlashFocus?: boolean;
  /** Suppress global slash focus shortcut (default: false) */
  suppressGlobalSlashFocus?: boolean;
}

export interface CommandInputRef {
  /** Focus the input */
  focus: () => void;
  /** Clear the input */
  clear: () => void;
  /** Set the input value */
  setValue: (value: string) => void;
}

/**
 * CommandInput - Unified input component for commands and chat
 * 
 * A flexible, multi-line input with optional slash command autocomplete.
 * Based on QuickTerminal's design with floating expansion behavior.
 * 
 * Features:
 * - Multi-line textarea with auto-expansion (1-5 lines)
 * - Floating effect when expanded beyond single line
 * - Optional slash command autocomplete
 * - Keyboard shortcuts (Enter, Shift+Enter, Escape, Ctrl+/)
 * - Slot-based icons and action buttons
 * - Consistent styling across all variants
 * 
 * @example
 * ```tsx
 * // QuickTerminal style (with slash commands)
 * <CommandInput
 *   value={value}
 *   onChange={setValue}
 *   onSubmit={handleSubmit}
 *   enableSlashCommands={true}
 *   availableCommands={["note", "link"]}
 *   onSlashCommand={handleSlashCommand}
 *   leftIcon={<FeatherTerminal />}
 *   rightActions={<>
 *     <DropdownMenu>...</DropdownMenu>
 *     <IconButton icon={<FeatherSparkles />} />
 *   </>}
 * />
 * 
 * // ChatInput style (no slash commands)
 * <CommandInput
 *   value={value}
 *   onChange={setValue}
 *   onSubmit={handleSend}
 *   placeholder="Ask me anything..."
 *   leftIcon={<FeatherSparkles />}
 *   rightActions={<IconButton icon={<FeatherSend />} />}
 * />
 * ```
 */
export const CommandInput = forwardRef<CommandInputRef, CommandInputProps>(
  (
    {
      value,
      onChange,
      onSubmit,
      placeholder = "Type / for commands or plain text",
      disabled = false,
      isLoading = false,
      multiline = true,
      minLines = 1,
      maxLines = 5,
      floatOnExpand = true,
      enableSlashCommands = false,
      availableCommands,
      onSlashCommand,
      leftIcon,
      rightActions,
      onEscape,
      submitOnEnter = true,
      allowShiftEnter = true,
      className = "",
      autoFocus = false,
      enableGlobalSlashFocus = false,
      suppressGlobalSlashFocus = false,
    },
    ref
  ) => {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const [textareaHeight, setTextareaHeight] = useState(minLines);

    // Slash command autocomplete (only if enabled)
    const slashCommands = useSlashCommands({
      inputValue: enableSlashCommands ? value : "",
      availableItemTypes: availableCommands,
      onSlashCommand: onSlashCommand || (() => {}),
    });

    // Expose imperative handle
    useImperativeHandle(ref, () => ({
      focus: () => textareaRef.current?.focus(),
      clear: () => onChange(""),
      setValue: (newValue: string) => onChange(newValue),
    }));

    // Calculate number of lines and adjust height
    useEffect(() => {
      if (textareaRef.current && multiline) {
        const lines = value.split("\n").length;
        setTextareaHeight(Math.max(minLines, Math.min(lines, maxLines)));
      }
    }, [value, multiline, minLines, maxLines]);

    const isEditableElement = (element: EventTarget | Element | null): boolean => {
      if (!(element instanceof Element)) return false;
      const editableSelector = "input, textarea, select, [contenteditable=\"\"], [contenteditable=\"true\"]";
      return !!element.closest(editableSelector);
    };

    const hasOpenDialog = (): boolean => {
      if (typeof document === "undefined") return false;

      if (document.querySelector("dialog[open]")) {
        return true;
      }

      const dialogElements = Array.from(document.querySelectorAll<HTMLElement>("[role='dialog']"));
      return dialogElements.some((dialogElement) => {
        if (dialogElement.getAttribute("data-state") === "open") return true;
        if (dialogElement.getAttribute("aria-hidden") === "false") return true;
        if (dialogElement.hasAttribute("open")) return true;
        return false;
      });
    };

    // Keyboard shortcut: / and Ctrl+/ (Win/Linux) or Cmd+/ (Mac) to focus input
    useEffect(() => {
      if (!enableGlobalSlashFocus) {
        return;
      }

      const handleKeyboardShortcut = (event: KeyboardEvent) => {
        const isComposing = event.isComposing;
        const targetIsEditable = isEditableElement(event.target);
        const activeIsEditable = isEditableElement(document.activeElement);
        const isSuppressed = suppressGlobalSlashFocus || hasOpenDialog();

        if (isComposing || targetIsEditable || activeIsEditable || isSuppressed) {
          return;
        }

        const slashKey = event.key === "/" || event.code === "Slash";
        const isPlainSlash = slashKey && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey;
        const isCtrlOrMetaSlash = slashKey && (event.ctrlKey || event.metaKey);

        if (!isPlainSlash && !isCtrlOrMetaSlash) {
          return;
        }

        event.preventDefault();
        textareaRef.current?.focus();
      };

      window.addEventListener("keydown", handleKeyboardShortcut);
      return () => window.removeEventListener("keydown", handleKeyboardShortcut);
    }, [enableGlobalSlashFocus, suppressGlobalSlashFocus]);

    // Handle Enter key
    const handleKeyDown = useCallback(
      async (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
        // Slash command navigation takes priority
        if (enableSlashCommands && slashCommands.handleKeyDown(event)) {
          return;
        }

        if (event.key === "Enter" && event.shiftKey && allowShiftEnter) {
          // Shift+Enter: Allow line break (default behavior)
          return;
        }

        if (event.key === "Enter" && !event.shiftKey && submitOnEnter) {
          event.preventDefault();

          const trimmedValue = value.trim();
          if (!trimmedValue) return;

          // Check if it's a slash command (and slash commands are enabled)
          if (enableSlashCommands && isSlashCommandInput(trimmedValue)) {
            if (slashCommands.showAutocomplete && slashCommands.filteredCommands.length > 0) {
              // Already handled by slashCommands.handleKeyDown
              return;
            } else {
              // Try to parse command directly
              const command = parseSlashCommand(trimmedValue);
              if (command && onSlashCommand) {
                onSlashCommand(command.type);
                onChange("");
              }
            }
          } else {
            // Submit plain text
            try {
              const submitResult = await onSubmit(trimmedValue);
              if (submitResult !== false) {
                onChange("");
              }
            } catch (error) {
              console.error("Failed to submit:", error);
              // Keep input value so user can retry
            }
          }
        } else if (event.key === "Escape") {
          event.preventDefault();
          if (onEscape) {
            onEscape();
          } else {
            onChange("");
          }
          slashCommands.closeAutocomplete();
        }
      },
      [
        value,
        enableSlashCommands,
        slashCommands,
        allowShiftEnter,
        submitOnEnter,
        onSlashCommand,
        onSubmit,
        onChange,
        onEscape,
      ]
    );

    const shouldFloat = floatOnExpand && textareaHeight > minLines;

    return (
      <div className={`relative flex w-full items-center gap-2 ${className}`} style={{ minHeight: "40px" }}>
        {/* Autocomplete Dropdown */}
        {enableSlashCommands && slashCommands.showAutocomplete && (
          <SlashCommandAutocomplete
            commands={slashCommands.filteredCommands}
            selectedIndex={slashCommands.selectedIndex}
            onSelect={slashCommands.handleSelect}
            onClose={slashCommands.closeAutocomplete}
          />
        )}

        {/* Multi-line Input Field with Icon */}
        <div className="flex-1 relative" style={{ height: "40px" }}>
          {/* Placeholder to maintain space when floating */}
          <div style={{ height: "40px" }} />

          {/* Container that floats above content when expanded */}
          <div
            className={`flex items-start gap-2 px-3 py-2 border border-solid border-neutral-border bg-default-background rounded-md transition-all focus-within:border-brand-primary focus-within:ring-1 focus-within:ring-brand-primary ${
              shouldFloat ? "absolute bottom-0 left-0 right-0 shadow-lg z-10" : "absolute bottom-0 left-0 right-0"
            }`}
            style={{
              minHeight: "40px",
            }}
          >
            {/* Left Icon - aligned to center when single line, top when multi-line */}
            {leftIcon && (
              <div className="flex-shrink-0 flex items-center" style={{ minHeight: "24px" }}>
                {leftIcon}
              </div>
            )}

            {/* Textarea */}
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => onChange(e.target.value || "")}
              onKeyDown={handleKeyDown}
              disabled={disabled || isLoading}
              placeholder={placeholder}
              autoFocus={autoFocus}
              className="flex-1 bg-transparent text-body font-body text-default-font placeholder:text-subtext-color outline-none resize-none overflow-y-auto"
              style={{
                minHeight: "24px",
                maxHeight: `${24 * maxLines}px`,
                height: `${24 * textareaHeight}px`,
                lineHeight: "24px",
              }}
              role={enableSlashCommands ? "combobox" : undefined}
              aria-expanded={enableSlashCommands ? slashCommands.showAutocomplete : undefined}
              aria-autocomplete={enableSlashCommands ? "list" : undefined}
              aria-controls={enableSlashCommands && slashCommands.showAutocomplete ? "slash-command-list" : undefined}
              aria-activedescendant={
                enableSlashCommands && slashCommands.showAutocomplete && slashCommands.filteredCommands[slashCommands.selectedIndex]
                  ? `slash-command-${slashCommands.filteredCommands[slashCommands.selectedIndex].command}`
                  : undefined
              }
            />
          </div>
        </div>

        {/* Right Actions */}
        {rightActions}
      </div>
    );
  }
);

CommandInput.displayName = "CommandInput";

export default CommandInput;
