import React, { useMemo, useState } from "react";

import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { TextField } from "@/components/forms/TextField";

import { CheckSquare, ChevronDown, ListFilter, Search, Square } from 'lucide-react';

export interface EventTypeSelectorProps {
  selectedEventTypes?: string[] | null;
  eventTypes: string[];
  isLoading?: boolean;
  disabled?: boolean;
  size?: "small" | "medium";
  onSelectionChange?: (eventTypes: string[] | null) => void;
  maxEventTypes?: number;
  className?: string;
  dropdownClassName?: string;
}

export const EventTypeSelector: React.FC<EventTypeSelectorProps> = ({
  selectedEventTypes,
  eventTypes,
  isLoading = false,
  disabled = false,
  size = "small",
  onSelectionChange,
  maxEventTypes,
  className,
  dropdownClassName,
}) => {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const selected = useMemo(() => selectedEventTypes || [], [selectedEventTypes]);

  const filteredEventTypes = useMemo(() => {
    if (!searchQuery) return eventTypes;
    const search = searchQuery.toLowerCase();
    return eventTypes.filter((eventType) => eventType.toLowerCase().includes(search));
  }, [eventTypes, searchQuery]);

  const displayEventTypes = maxEventTypes
    ? filteredEventTypes.slice(0, maxEventTypes)
    : filteredEventTypes;

  const buttonLabel = useMemo(() => {
    if (disabled) return "Updating...";
    if (selected.length === 0) return "All event types";
    if (selected.length === 1) return selected[0];
    if (selected.length === 2) return selected.join(", ");
    return `${selected.length} event types`;
  }, [disabled, selected]);

  const handleToggle = (eventType: string) => {
    if (!onSelectionChange) return;

    const nextSelection = selected.includes(eventType)
      ? selected.filter((value) => value !== eventType)
      : [...selected, eventType];

    onSelectionChange(nextSelection.length > 0 ? nextSelection : null);
  };

  const handleClearSelection = () => {
    onSelectionChange?.(null);
  };

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
          icon={<ListFilter />}
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
        {eventTypes.length > 0 && (
          <div className="w-full border-b border-neutral-border px-2 py-2">
            <TextField
              className="h-8 w-full"
              variant="filled"
              label=""
              helpText=""
              icon={<Search />}
            >
              <TextField.Input
                placeholder="Quick filter event types"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onKeyDown={(event) => event.stopPropagation()}
              />
            </TextField>
          </div>
        )}

        {isLoading ? (
          <DropdownMenu.DropdownItem icon={null} label="Loading event types..." />
        ) : displayEventTypes.length > 0 ? (
          displayEventTypes.map((eventType) => {
            const isSelected = selected.includes(eventType);

            return (
              <DropdownMenu.DropdownItem
                key={eventType}
                icon={isSelected ? <CheckSquare /> : <Square />}
                label={eventType}
                onClick={() => handleToggle(eventType)}
                onSelect={(event) => event.preventDefault()}
              />
            );
          })
        ) : searchQuery ? (
          <DropdownMenu.DropdownItem icon={null} label="No event types found" />
        ) : (
          <DropdownMenu.DropdownItem icon={null} label="No event types available" />
        )}

        {eventTypes.length > 0 ? (
          <>
            <DropdownMenu.DropdownDivider />
            <DropdownMenu.DropdownItem
              icon={null}
              hint=""
              label="Clear selection"
              onClick={handleClearSelection}
            />
          </>
        ) : null}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};