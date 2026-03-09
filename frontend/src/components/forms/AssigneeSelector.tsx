import React, { useState, useMemo } from "react";
import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { TextField } from "@/components/forms/TextField";
import type { app__api__routes__admin_auth__UserSummary } from "@/types/generated/models/app__api__routes__admin_auth__UserSummary";

import { CheckSquare, ChevronDown, Search, Square, User, UserPlus, UserX } from 'lucide-react';
export interface AssigneeSelectorProps {
  /** Mode: 'assign' for single assignment, 'filter' for multi-select filtering */
  mode?: "assign" | "filter";
  /** Current assignee username (null if unassigned) - for 'assign' mode */
  currentAssignee?: string | null;
  /** Selected assignees - for 'filter' mode (supports multiple selections) */
  selectedAssignees?: string[] | null;
  /** Current logged-in user's username */
  currentUser: string | null;
  /** List of available users */
  users: app__api__routes__admin_auth__UserSummary[];
  /** Whether users are loading */
  isLoadingUsers?: boolean;
  /** Whether the selector is disabled (e.g., during mutation) */
  disabled?: boolean;
  /** Size variant: 'small' for filters (default), 'medium' for headers */
  size?: "small" | "medium";
  /** Callback when user selects to unassign - for 'assign' mode */
  onUnassign?: () => void;
  /** Callback when user selects "Assign to me" - for 'assign' mode */
  onAssignToMe?: () => void;
  /** Callback when user selects a specific user - for 'assign' mode */
  onAssignToUser?: (username: string) => void;
  /** Callback when assignee selection changes - for 'filter' mode */
  onSelectionChange?: (assignees: string[] | null) => void;
  /** Maximum number of users to show in list (default: all) */
  maxUsers?: number;
  /** Optional className for the button */
  className?: string;
  /** Optional className for the dropdown menu content */
  dropdownClassName?: string;
}

/**
 * AssigneeSelector - A reusable dropdown component for assigning items to users or filtering by assignees.
 * 
 * Features:
 * - Two modes: 'assign' (single selection) and 'filter' (multi-select)
 * - Two sizes: 'small' (default, h-8) for filters and 'medium' (h-9, matches header buttons) for headers
 * - Search/filter input in dropdown for all contexts
 * - Assignment mode: Shows current assignment status, Assign to me, Unassign options
 * - Filter mode: Multi-select with checkboxes, shows "Unassigned" and "Clear selection"
 * - Smart hints showing assignment status and email
 * - Automatic dropdown close after selection (in assign mode)
 * 
 * @example Assignment Mode (in filters)
 * ```tsx
 * <AssigneeSelector
 *   mode="assign"
 *   size="small"
 *   currentAssignee={alert.assignee}
 *   currentUser={user?.username || null}
 *   users={users}
 *   isLoadingUsers={isLoadingUsers}
 *   disabled={updateMutation.isPending}
 *   onUnassign={handleUnassign}
 *   onAssignToMe={handleAssignToMe}
 *   onAssignToUser={handleAssignToUser}
 * />
 * ```
 * 
 * @example Assignment Mode (in header)
 * ```tsx
 * <AssigneeSelector
 *   mode="assign"
 *   size="medium"
 *   currentAssignee={alert.assignee}
 *   currentUser={user?.username || null}
 *   users={users}
 *   isLoadingUsers={isLoadingUsers}
 *   disabled={updateMutation.isPending}
 *   onUnassign={handleUnassign}
 *   onAssignToMe={handleAssignToMe}
 *   onAssignToUser={handleAssignToUser}
 * />
 * ```
 * 
 * @example Filter Mode
 * ```tsx
 * <AssigneeSelector
 *   mode="filter"
 *   selectedAssignees={filters.assignee}
 *   currentUser={user?.username || null}
 *   users={users}
 *   isLoadingUsers={isLoadingUsers}
 *   onSelectionChange={(assignees) => updateFilter('assignee', assignees)}
 * />
 * ```
 */
export const AssigneeSelector: React.FC<AssigneeSelectorProps> = ({
  mode = "assign",
  currentAssignee,
  selectedAssignees,
  currentUser,
  users,
  isLoadingUsers = false,
  disabled = false,
  size = "small",
  onUnassign,
  onAssignToMe,
  onAssignToUser,
  onSelectionChange,
  maxUsers,
  className,
  dropdownClassName,
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  // Check if current item is assigned to current user (assign mode)
  const isAssignedToCurrentUser = mode === "assign" && currentUser && currentAssignee === currentUser;

  // Get selected assignees for filter mode
  const selected = useMemo(() => {
    if (mode !== "filter") {
      return [];
    }
    return selectedAssignees || [];
  }, [mode, selectedAssignees]);

  // Filter users by search query
  const filteredUsers = useMemo(() => {
    if (!searchQuery) return users;
    const search = searchQuery.toLowerCase();
    return users.filter(
      (user) =>
        user.username.toLowerCase().includes(search) ||
        user.email?.toLowerCase().includes(search)
    );
  }, [users, searchQuery]);

  // Determine users to display (with optional limit)
  const displayUsers = maxUsers ? filteredUsers.slice(0, maxUsers) : filteredUsers;

  // Get button label based on mode
  const buttonLabel = useMemo(() => {
    if (disabled) return "Updating...";

    if (mode === "assign") {
      return currentAssignee
        ? `${currentAssignee}${isAssignedToCurrentUser ? " (You)" : ""}`
        : "Unassigned";
    } else {
      // Filter mode
      if (selected.length === 0) return "Assignee";
      if (selected.length === 1) {
        if (selected[0] === "__unassigned__") return "Unassigned";
        const user = users.find((u) => u.username === selected[0]);
        return user ? user.username : selected[0];
      }
      if (selected.length === 2) {
        const formatted = selected.map((a) =>
          a === "__unassigned__" ? "Unassigned" : a
        );
        return formatted.join(", ");
      }
      return `${selected.length} assignees`;
    }
  }, [mode, disabled, currentAssignee, isAssignedToCurrentUser, selected, users]);

  // Handle assignee toggle for filter mode
  const handleToggle = (username: string) => {
    if (mode !== "filter" || !onSelectionChange) return;

    const newSelection = selected.includes(username)
      ? selected.filter((a) => a !== username) // Remove if present
      : [...selected, username]; // Add if not present

    onSelectionChange(newSelection.length > 0 ? newSelection : null);
  };

  // Handle clear selection for filter mode
  const handleClearSelection = () => {
    if (mode === "filter" && onSelectionChange) {
      onSelectionChange(null);
    }
  };

  // Handle assignment actions for assign mode
  const handleAssign = (action: "unassign" | "assignToMe" | string) => {
    if (mode !== "assign") return;

    if (action === "unassign" && onUnassign) {
      onUnassign();
      setDropdownOpen(false);
    } else if (action === "assignToMe" && onAssignToMe) {
      onAssignToMe();
      setDropdownOpen(false);
    } else if (onAssignToUser) {
      onAssignToUser(action);
      setDropdownOpen(false);
    }
  };

  // Clear search when dropdown closes
  const handleOpenChange = (open: boolean) => {
    setDropdownOpen(open);
    if (!open) {
      setSearchQuery("");
    }
  };

  return (
    <DropdownMenu.Root modal={false} open={dropdownOpen} onOpenChange={handleOpenChange}>
      <DropdownMenu.Trigger asChild>
        <Button
          className={className || (size === "medium" ? "h-auto w-auto flex-none self-stretch" : "h-8 w-auto")}
          variant="neutral-secondary"
          size={size}
          icon={<User />}
          iconRight={<ChevronDown />}
          disabled={disabled}
        >
          {buttonLabel}
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content
        side="bottom"
        align="start"
        sideOffset={4}
        className={`max-h-[400px] overflow-y-auto ${dropdownClassName || ""}`}
      >
            {/* Search input - always visible */}
            {users.length > 0 && (
              <div className="w-full px-2 py-2 border-b border-neutral-border">
                <TextField
                  className="h-8 w-full"
                  variant="filled"
                  label=""
                  helpText=""
                  icon={<Search />}
                >
                  <TextField.Input
                    placeholder="Search users..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.stopPropagation()}
                  />
                </TextField>
              </div>
            )}

            {/* Assign Mode - Static Actions */}
            {mode === "assign" && (
              <>
                {/* Unassign option (only show if currently assigned) */}
                {currentAssignee && onUnassign && (
                  <>
                    <DropdownMenu.DropdownItem
                      icon={<UserX />}
                      label="Unassign"
                      onClick={() => handleAssign("unassign")}
                    />
                    <DropdownMenu.DropdownDivider />
                  </>
                )}

                {/* Assign to me option (hide if already assigned to current user) */}
                {currentUser && onAssignToMe && !isAssignedToCurrentUser && (
                  <>
                    <DropdownMenu.DropdownItem
                      icon={<UserPlus />}
                      label="Assign to me"
                      onClick={() => handleAssign("assignToMe")}
                    />
                    <DropdownMenu.DropdownDivider />
                  </>
                )}
              </>
            )}

            {/* Filter Mode - Unassigned Option */}
            {mode === "filter" && (
              <>
                <DropdownMenu.DropdownItem
                  icon={
                    selected.includes("__unassigned__") ? (
                      <CheckSquare />
                    ) : (
                      <Square />
                    )
                  }
                  hint="Items with no assignee"
                  label="Unassigned"
                  onClick={() => handleToggle("__unassigned__")}
                  onSelect={(e) => e.preventDefault()}
                />
                {users.length > 0 && <DropdownMenu.DropdownDivider />}
              </>
            )}

            {/* User List */}
            {isLoadingUsers ? (
              <DropdownMenu.DropdownItem icon={null} label="Loading users..." />
            ) : displayUsers.length > 0 ? (
              displayUsers.map((user) => {
                const isSelected = mode === "filter" && selected.includes(user.username);
                const isCurrent = user.username === currentAssignee;

                return (
                  <DropdownMenu.DropdownItem
                    key={user.userId}
                    icon={
                      mode === "filter" ? (
                        isSelected ? (
                          <CheckSquare />
                        ) : (
                          <Square />
                        )
                      ) : (
                        <User />
                      )
                    }
                    label={user.username}
                    hint={
                      mode === "assign"
                        ? isCurrent
                          ? "Currently assigned"
                          : user.username === currentUser
                          ? "You"
                          : user.email
                        : user.email
                    }
                    onClick={() =>
                      mode === "filter"
                        ? handleToggle(user.username)
                        : handleAssign(user.username)
                    }
                    onSelect={(e) => {
                      if (mode === "filter") {
                        e.preventDefault();
                      }
                    }}
                  />
                );
              })
            ) : searchQuery ? (
              <DropdownMenu.DropdownItem icon={null} label="No users found" />
            ) : (
              <DropdownMenu.DropdownItem icon={null} label="No users available" />
            )}

            {/* Filter Mode - Clear Selection */}
            {mode === "filter" && users.length > 0 && (
              <>
                <DropdownMenu.DropdownDivider />
                <DropdownMenu.DropdownItem
                  icon={null}
                  hint=""
                  label="Clear selection"
                  onClick={handleClearSelection}
                />
              </>
            )}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
