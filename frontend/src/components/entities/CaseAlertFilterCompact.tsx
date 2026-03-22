
"use client";

import React from "react";
import type { FilterState } from "@/types/filters";
import type { AlertStatus } from "@/types/generated/models/AlertStatus";
import type { app__api__routes__admin_auth__UserSummary } from "@/types/generated/models/app__api__routes__admin_auth__UserSummary";
import { AssigneeSelector } from "@/components/forms/AssigneeSelector";
import { DateRangePicker, DateRangeValue } from "@/components/forms/DateRangePicker";





import { cn } from "@/utils/cn";
import { Button } from "@/components/buttons/Button";
import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { formatStatusLabel } from "@/utils/formatters";

import { CheckSquare, ChevronDown, FileText, RotateCcw, Square } from 'lucide-react';
interface StatusOption {
  value: string;
  label: string;
}

interface CaseAlertFilterCompactRootProps
  extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
  /** Current filter state */
  filters?: FilterState;
  /** Callback when filters change */
  onFilterChange?: (filters: FilterState) => void;
  /** List of assignees for dropdown */
  assignees?: app__api__routes__admin_auth__UserSummary[];
  /** Whether assignees are loading */
  assigneesLoading?: boolean;
  /** Options for status filter */
  statusOptions?: StatusOption[];
}

const CaseAlertFilterCompactRoot = React.forwardRef<
  HTMLDivElement,
  CaseAlertFilterCompactRootProps
>(function CaseAlertFilterCompactRoot(
  { className, filters, onFilterChange, assignees = [], assigneesLoading = false, statusOptions, ...otherProps }: CaseAlertFilterCompactRootProps,
  ref
) {
  // Local state for assignee search
  const [assigneeSearch, setAssigneeSearch] = React.useState<string>('');

  // Detect if we're on mobile breakpoint
  const [isMobile, setIsMobile] = React.useState(false);
  
  React.useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768); // md breakpoint
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Default status options (AlertStatus) - uses UPPERCASE API enum values
  const defaultStatusOptions: StatusOption[] = [
    { value: 'NEW', label: 'New' },
    { value: 'IN_PROGRESS', label: 'In Progress' },
    { value: 'ESCALATED', label: 'Escalated' },
    { value: 'CLOSED_TP', label: 'Closed (True Positive)' },
    { value: 'CLOSED_BP', label: 'Closed (Benign Positive)' },
    { value: 'CLOSED_FP', label: 'Closed (False Positive)' },
    { value: 'CLOSED_UNRESOLVED', label: 'Closed (Unresolved)' },
    { value: 'CLOSED_DUPLICATE', label: 'Closed (Duplicate)' },
  ];

  const effectiveStatusOptions = statusOptions || defaultStatusOptions;

  // Helper to update a single filter field
  const updateFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    if (onFilterChange) {
      onFilterChange({
        ...filters,
        [key]: value,
      } as FilterState);
    }
  };

  // Helper to reset all filters
  const handleReset = () => {
    if (onFilterChange) {
      onFilterChange({
        search: '',
        assignee: null,
        status: null,
        dateRange: null,
      });
    }
  };

  // Get label for status button based on number of selected statuses
  const statusLabel = React.useMemo(() => {
    if (!filters?.status || filters.status.length === 0) return 'Status';
    
    // On mobile, always show count format if multiple selected
    if (isMobile && filters.status.length > 1) {
      return `${filters.status.length} statuses`;
    }
    
    const getLabel = (status: string) => {
      const option = effectiveStatusOptions.find(o => o.value === status);
      return option ? option.label : formatStatusLabel(status as AlertStatus);
    };

    if (filters.status.length === 1) return getLabel(filters.status[0]);
    if (filters.status.length === 2) {
      return filters.status.map(s => getLabel(s as string)).join(', ');
    }
    return `${filters.status.length} statuses`;
  }, [filters?.status, isMobile, effectiveStatusOptions]);

  // Handler for toggling individual status selections
  const handleStatusToggle = (status: string) => {
    const current = (filters?.status || []) as string[];
    const newStatuses = current.includes(status)
      ? current.filter(s => s !== status)  // Remove if present
      : [...current, status];              // Add if not present

    updateFilter('status', newStatuses.length > 0 ? newStatuses as any : null);
  };

  return (
    <div
      className={cn(
        "flex w-full flex-wrap items-start justify-end gap-2",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <div className="flex grow shrink-0 basis-0 flex-col flex-wrap items-center gap-2">
        <div className="flex w-full min-w-[192px] flex-wrap items-center gap-2">
          <div className="flex grow shrink-0 basis-0 items-center gap-2">
            <AssigneeSelector
              mode="filter"
              selectedAssignees={filters?.assignee}
              currentUser={null}
              users={assignees}
              isLoadingUsers={assigneesLoading}
              onSelectionChange={(assignees) => updateFilter('assignee', assignees)}
              className="h-8 grow shrink-0 basis-0"
            />
            <DropdownMenu.Root>
              <DropdownMenu.Trigger asChild>
                <Button
                  className="h-8 grow shrink-0 basis-0"
                  variant="neutral-secondary"
                  size="small"
                  icon={<FileText />}
                  iconRight={<ChevronDown />}
                >
                  {statusLabel}
                </Button>
              </DropdownMenu.Trigger>
              <DropdownMenu.Content
                side="bottom"
                align="start"
                sideOffset={4}
              >
                    {effectiveStatusOptions.map((option) => (
                      <DropdownMenu.DropdownItem
                        key={option.value}
                        icon={(filters?.status || []).includes(option.value as any) ? <CheckSquare /> : <Square />}
                        hint=""
                        label={option.label}
                        onClick={() => handleStatusToggle(option.value)}
                        onSelect={(e) => e.preventDefault()}
                      />
                    ))}
                    <DropdownMenu.DropdownDivider />
                    <DropdownMenu.DropdownItem
                      icon={null}
                      hint=""
                      label="Clear selection"
                      onClick={() => updateFilter('status', null)}
                    />
              </DropdownMenu.Content>
            </DropdownMenu.Root>
            <DateRangePicker
              className="h-8 grow shrink-0 basis-0"
              value={filters?.dateRange as DateRangeValue | null}
              onChange={(value) => updateFilter('dateRange', value)}
              size="small"
              variant="neutral-secondary"
            />
          </div>
          {/* Reset button */}
          <Button
            className="h-8 w-auto flex-none"
            variant="brand-tertiary"
            size="small"
            icon={<RotateCcw />}
            onClick={handleReset}
          />
        </div>
      </div>
    </div>
  );
});

export const CaseAlertFilterCompact = CaseAlertFilterCompactRoot;
