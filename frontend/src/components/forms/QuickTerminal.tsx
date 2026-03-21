/**
 * Quick Terminal Component
 * 
 * Generic text input for rapid note-taking and slash command initiation.
 * Can be used in multiple contexts (alerts, cases, inline replies).
 * 
 * Features:
 * - Plain text note submission on Enter key
 * - Slash command detection and autocomplete
 * - Escape key to clear input
 * - Context-aware (supports alerts, cases, and future entity types)
 * - Configurable timeline item types (filters dropdown and slash commands)
 * 
 * Design Decision: NO DRAFT AUTO-SAVE
 * The quick terminal is designed for rapid, ephemeral note-taking.
 * Only the right dock forms (full forms) persist drafts, as they're meant
 * for more thoughtful, structured content. This prevents confusion where
 * a draft from the right dock rehydrates into the quick terminal.
 * 
 * @example
 * // Usage on Alerts page with all alert-supported types
 * <QuickTerminal
 *   entityId={alertId}
 *   entityType="alert"
 *   availableItemTypes={[
 *     "note", "attachment", "link", "observable", "system", 
 *     "actor", "email", "network_traffic", "process", "registry_change", "ttp"
 *   ]}
 *   onSlashCommand={handleSlashCommand}
 *   onSubmitNote={handleSubmitNote}
 *   onAddNote={handleAddNote}
 *   onMenuItemSelect={handleMenuItemSelect}
 *   disabled={isAlertClosed}
 *   isSubmitting={mutation.isPending}
 * />
 * 
 * @example
 * // Usage on Cases page with case-supported types (future)
 * <QuickTerminal
 *   entityId={caseId}
 *   entityType="case"
 *   availableItemTypes={[
 *     "note", "attachment", "link", "task", "actor", "system",
 *     "observable", "email", "network_traffic", "process", "registry_change", "ttp", "forensic_artifact"
 *   ]}
 *   onSlashCommand={handleSlashCommand}
 *   onSubmitNote={handleSubmitNote}
 *   onAddNote={handleAddNote}
 *   onMenuItemSelect={handleMenuItemSelect}
 * />
 * 
 * @example
 * // Usage inline within a reply thread (limited types)
 * <QuickTerminal
 *   entityId={parentItemId}
 *   entityType="alert"
 *   availableItemTypes={["note", "link", "attachment"]}
 *   onSlashCommand={handleReplySlashCommand}
 *   onSubmitNote={handleSubmitReply}
 *   onAddNote={handleAddReplyNote}
 *   onMenuItemSelect={handleReplyMenuItemSelect}
 * />
 */

import React, { useState, useCallback } from "react";

import { IconButton } from "@/components/buttons/IconButton";
import { DropdownMenu, DropdownMenuRoot, DropdownMenuTrigger, DropdownMenuContent } from "@/components/overlays/DropdownMenu";
import { TIMELINE_ICONS } from "@/utils/timelineMapping";
import type { TimelineItemType } from "@/types/drafts";
import { CommandInput } from "@/components/forms/CommandInput";
import { SLASH_COMMANDS } from "@/utils/slashCommands";

import { Menu, Sparkles, Terminal } from 'lucide-react';
/**
 * Entity type for generic timeline item creation
 */
export type EntityType = "alert" | "case" | "task";

export interface QuickTerminalProps {
  /** Entity ID for timeline item creation (e.g., alert ID or case ID) */
  entityId: number;
  /** Entity type (alert, case, etc.) */
  entityType: EntityType;
  /** Optional: Parent item ID for replies */
  parentItemId?: string;
  /** Callback when slash command is triggered */
  onSlashCommand: (itemType: TimelineItemType) => void;
  /** Callback when plain text note should be submitted */
  onSubmitNote: (text: string, parentItemId?: string) => Promise<void>;
  /** Callback when "Add Note" button clicked (from menu) */
  onAddNote: () => void;
  /** Callback for dropdown menu item selection */
  onMenuItemSelect: (itemType: TimelineItemType) => void;
  /** Whether terminal is disabled */
  disabled?: boolean;
  /** Whether submission is in progress */
  isSubmitting?: boolean;
  /** Optional: Filter which timeline item types are available. If not provided, all types are shown. */
  availableItemTypes?: TimelineItemType[];
  /** Optional: Show AI chat button (only for cases/tasks, not alerts) */
  showAiChatButton?: boolean;
  /** Optional: Callback when AI chat button is clicked */
  onAiChatClick?: () => void;
  /** Optional: Enable global slash focus shortcut for this terminal */
  enableGlobalSlashFocus?: boolean;
  /** Optional: Suppress global slash focus shortcut for this terminal */
  suppressGlobalSlashFocus?: boolean;
  /** Callback when files are pasted from clipboard (e.g. screenshots) */
  onPasteFiles?: (files: File[]) => void;
}

export function QuickTerminal({
  entityId,
  entityType,
  parentItemId,
  onSlashCommand,
  onSubmitNote,
  onAddNote,
  onMenuItemSelect,
  disabled = false,
  isSubmitting = false,
  availableItemTypes,
  showAiChatButton = false,
  onAiChatClick,
  enableGlobalSlashFocus = false,
  suppressGlobalSlashFocus = false,
  onPasteFiles,
}: QuickTerminalProps) {
  const [inputValue, setInputValue] = useState("");

  // NOTE: No draft auto-save for quick terminal - it's meant for rapid, ephemeral notes.
  // Only the right dock forms persist drafts for more thoughtful, structured content.

  // Helper to check if an item type is available
  const isItemTypeAvailable = useCallback((itemType: TimelineItemType) => {
    if (!availableItemTypes) return true; // If not specified, all types are available
    return availableItemTypes.includes(itemType);
  }, [availableItemTypes]);

  // Handle submit
  const handleSubmit = useCallback(
    async (text: string) => {
      try {
        await onSubmitNote(text, parentItemId);
      } catch (error) {
        console.error("Failed to submit note:", error);
        throw error; // Re-throw to keep input value
      }
    },
    [onSubmitNote, parentItemId]
  );

  return (
    <CommandInput
      value={inputValue}
      onChange={setInputValue}
      onSubmit={handleSubmit}
      placeholder="Type / for commands or plain text for quick note (Ctrl+/)"
      disabled={disabled}
      isLoading={isSubmitting}
      multiline={true}
      minLines={1}
      maxLines={5}
      floatOnExpand={true}
      enableSlashCommands={true}
      availableCommands={availableItemTypes}
      onSlashCommand={onSlashCommand}
      enableGlobalSlashFocus={enableGlobalSlashFocus}
      suppressGlobalSlashFocus={suppressGlobalSlashFocus}
      onPasteFiles={onPasteFiles}
      leftIcon={<Terminal className="text-subtext-color" />}
      rightActions={
        <>
          {/* Dropdown Menu for timeline item types */}
          <div className="flex-shrink-0" style={{ height: '40px' }}>
            <DropdownMenuRoot>
              <DropdownMenuTrigger asChild={true}>
                <IconButton
                  icon={<Menu />}
                  size="large"
                  variant="neutral-tertiary"
                  disabled={disabled || isSubmitting}
                  aria-label="Add timeline item"
                />
              </DropdownMenuTrigger>
            <DropdownMenuContent
                side="top"
                align="end"
                sideOffset={4}
              >
                  {/* Note - always at top when available */}
                  {isItemTypeAvailable("note") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.note />}
                      hint={SLASH_COMMANDS.find(c => c.type === "note")?.label}
                      showHint={true}
                      label="Note"
                      onClick={onAddNote}
                    />
                  )}
                  {isItemTypeAvailable("note") && (isItemTypeAvailable("attachment") || isItemTypeAvailable("link") || isItemTypeAvailable("task")) && (
                    <DropdownMenu.DropdownDivider />
                  )}
                  {isItemTypeAvailable("attachment") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.attachment />}
                      hint={SLASH_COMMANDS.find(c => c.type === "attachment")?.label}
                      showHint={true}
                      label="Attachment"
                      onClick={() => onMenuItemSelect("attachment")}
                    />
                  )}
                  {isItemTypeAvailable("link") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.link />}
                      hint={SLASH_COMMANDS.find(c => c.type === "link")?.label}
                      showHint={true}
                      label="Link"
                      onClick={() => onMenuItemSelect("link")}
                    />
                  )}
                  {isItemTypeAvailable("task") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.task />}
                      hint={SLASH_COMMANDS.find(c => c.type === "task")?.label}
                      showHint={true}
                      label="Task"
                      onClick={() => onMenuItemSelect("task")}
                    />
                  )}
                  {(isItemTypeAvailable("actor") || isItemTypeAvailable("system")) && (
                    <DropdownMenu.DropdownDivider />
                  )}
                  {isItemTypeAvailable("actor") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.actor />}
                      hint={SLASH_COMMANDS.find(c => c.type === "actor")?.label}
                      showHint={true}
                      label="Actor"
                      onClick={() => onMenuItemSelect("actor")}
                    />
                  )}
                  {isItemTypeAvailable("system") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.system />}
                      hint={SLASH_COMMANDS.find(c => c.type === "system")?.label}
                      showHint={true}
                      label="System"
                      onClick={() => onMenuItemSelect("system")}
                    />
                  )}
                  {isItemTypeAvailable("observable") && (
                    <>
                      <DropdownMenu.DropdownDivider />
                      <DropdownMenu.DropdownItem
                        icon={<TIMELINE_ICONS.observable />}
                        hint={SLASH_COMMANDS.find(c => c.type === "observable")?.label}
                        showHint={true}
                        label="Observable (IOC)"
                        onClick={() => onMenuItemSelect("observable")}
                      />
                    </>
                  )}
                  {(isItemTypeAvailable("email") || isItemTypeAvailable("forensic_artifact") || 
                    isItemTypeAvailable("network_traffic") || isItemTypeAvailable("registry_change") || 
                    isItemTypeAvailable("ttp")) && (
                    <DropdownMenu.DropdownDivider />
                  )}
                  {isItemTypeAvailable("email") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.email />}
                      hint={SLASH_COMMANDS.find(c => c.type === "email")?.label}
                      showHint={true}
                      label="Email"
                      onClick={() => onMenuItemSelect("email")}
                    />
                  )}
                  {isItemTypeAvailable("forensic_artifact") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.forensic_artifact />}
                      hint={SLASH_COMMANDS.find(c => c.type === "forensic_artifact")?.label}
                      showHint={true}
                      label="Forensic Artifact"
                      onClick={() => onMenuItemSelect("forensic_artifact")}
                    />
                  )}
                  {isItemTypeAvailable("network_traffic") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.network_traffic />}
                      hint={SLASH_COMMANDS.find(c => c.type === "network_traffic")?.label}
                      showHint={true}
                      label="Network Comms"
                      onClick={() => onMenuItemSelect("network_traffic")}
                    />
                  )}
                  {isItemTypeAvailable("registry_change") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.registry_change />}
                      hint={SLASH_COMMANDS.find(c => c.type === "registry_change")?.label}
                      showHint={true}
                      label="Registry Change"
                      onClick={() => onMenuItemSelect("registry_change")}
                    />
                  )}
                  {isItemTypeAvailable("ttp") && (
                    <DropdownMenu.DropdownItem
                      icon={<TIMELINE_ICONS.ttp />}
                      hint={SLASH_COMMANDS.find(c => c.type === "ttp")?.label}
                      showHint={true}
                      label="TTP"
                      onClick={() => onMenuItemSelect("ttp")}
                    />
                  )}
              </DropdownMenuContent>
          </DropdownMenuRoot>
          </div>

          {/* AI Chat Button - only shown for cases/tasks with AI chat enabled */}
          {showAiChatButton && onAiChatClick && (
            <div className="flex-shrink-0" style={{ height: '40px' }}>
              <IconButton
                size="large"
                variant="brand-tertiary"
                icon={<Sparkles />}
                onClick={onAiChatClick}
                disabled={disabled || isSubmitting}
                aria-label="Open AI Chat"
              />
            </div>
          )}
        </>
      }
    />
  );
}
