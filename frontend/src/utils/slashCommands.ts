/**
 * Slash command registry and parsing utilities
 */

import type { TimelineItemType } from "@/types/drafts";

/**
 * Slash command definition
 */
export interface SlashCommand {
  /** Command string (e.g., "ioc") */
  command: string;
  /** Timeline item type this command creates */
  type: TimelineItemType;
  /** Display label for the command */
  label: string;
  /** Description shown in autocomplete */
  description: string;
}

/**
 * Registry of all available slash commands
 */
export const SLASH_COMMANDS: SlashCommand[] = [
  {
    command: "note",
    type: "note",
    label: "/note",
    description: "Add a note with markdown support",
  },
  {
    command: "ioc",
    type: "observable",
    label: "/ioc",
    description: "Add an Observable (IOC)",
  },
  {
    command: "sys",
    type: "system",
    label: "/sys",
    description: "Add a System",
  },
  {
    command: "act",
    type: "actor",
    label: "/act",
    description: "Add an Actor (user)",
  },
  {
    command: "eml",
    type: "email",
    label: "/eml",
    description: "Add an Email",
  },
  {
    command: "lnk",
    type: "link",
    label: "/lnk",
    description: "Add a Link",
  },
  {
    command: "tsk",
    type: "task",
    label: "/tsk",
    description: "Add a Task",
  },
  {
    command: "att",
    type: "attachment",
    label: "/att",
    description: "Upload an Attachment",
  },
  {
    command: "net",
    type: "network_traffic",
    label: "/net",
    description: "Add Network Communications",
  },
  {
    command: "prc",
    type: "process",
    label: "/prc",
    description: "Add a Process",
  },
  {
    command: "reg",
    type: "registry_change",
    label: "/reg",
    description: "Add a Registry Change",
  },
  {
    command: "ttp",
    type: "ttp",
    label: "/ttp",
    description: "Add a TTP (MITRE ATT&CK)",
  },
  {
    command: "art",
    type: "forensic_artifact",
    label: "/art",
    description: "Add a Forensic Artifact",
  },
];

/**
 * Parse input to detect slash command
 * @param input User input string
 * @returns Matched slash command or null
 */
export function parseSlashCommand(input: string): SlashCommand | null {
  // Match slash commands at start of input
  const match = input.match(/^\/([a-z]+)/i);
  if (!match) return null;

  const commandStr = match[1].toLowerCase();
  return SLASH_COMMANDS.find((cmd) => cmd.command === commandStr) || null;
}

/**
 * Filter slash commands by query string
 * @param query User input (e.g., "/io" or "/sys")
 * @returns Filtered list of matching commands
 */
export function filterSlashCommands(query: string): SlashCommand[] {
  // Remove leading slash for matching
  const searchTerm = query.startsWith("/") ? query.slice(1).toLowerCase() : query.toLowerCase();

  if (!searchTerm) {
    // Return all commands if just "/" typed
    return SLASH_COMMANDS;
  }

  // Filter by command string
  return SLASH_COMMANDS.filter((cmd) => cmd.command.startsWith(searchTerm));
}

/**
 * Check if input starts with a slash command
 * @param input User input string
 * @returns True if input starts with "/"
 */
export function isSlashCommandInput(input: string): boolean {
  return input.startsWith("/");
}
