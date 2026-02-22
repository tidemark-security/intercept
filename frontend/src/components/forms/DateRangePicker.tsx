"use client";
/**
 * DateRangePicker - Reusable date range selection component
 * 
 * Extracted from CaseAlertFilterCompact for reuse in GlobalSearch and other contexts.
 * Provides relative time presets, custom range input, and timezone-aware display.
 */

import React from "react";

import { DropdownMenu } from "@/components/overlays/DropdownMenu";
import { Accordion } from "@/components/misc/Accordion";
import { Button } from "@/components/buttons/Button";
import { TextField } from "@/components/forms/TextField";
import { Calendar, ChevronDown } from 'lucide-react';
import {
  formatForBackend,
  parseISO8601,
  parseRelativeTime,
  isValidDateRange,
  formatForDisplay,
  getUserTimezone,
  getRelativeTimeLabel,
} from "@/utils/dateFilters";

/** Date range value with start/end times and optional preset indicator */
export interface DateRangeValue {
  start: string;  // ISO8601 UTC string
  end: string;    // ISO8601 UTC string
  preset?: string; // Relative expression like "-7d" or "custom"
}

export interface DateRangePickerProps {
  /** Current value - null means "All time" (no filter) */
  value: DateRangeValue | null;
  /** Callback when value changes */
  onChange: (value: DateRangeValue | null) => void;
  /** Custom presets (default: ['-15m', '-1h', '-24h', '-7d', '-30d', '-90d']) */
  presets?: string[];
  /** Whether to show "All time" option (default: true) */
  showAllTime?: boolean;
  /** Button size variant */
  size?: "small" | "medium";
  /** Additional CSS classes */
  className?: string;
  /** Button variant */
  variant?: "neutral-secondary" | "neutral-tertiary";
}

export function DateRangePicker({
  value,
  onChange,
  presets = ['-15m', '-1h', '-24h', '-7d', '-30d', '-90d'],
  showAllTime = true,
  size = "small",
  className,
  variant = "neutral-secondary",
}: DateRangePickerProps) {
  // Local state for custom date range inputs
  const [customStart, setCustomStart] = React.useState<string>('');
  const [customEnd, setCustomEnd] = React.useState<string>('');
  const [dateError, setDateError] = React.useState<string | null>(null);
  const [isOpen, setIsOpen] = React.useState(false);

  // Get user's timezone for display
  const userTimezone = React.useMemo(() => getUserTimezone(), []);

  // Handle preset button clicks
  const handlePresetClick = (relativeExpression: string | null) => {
    // Special case: null means "All time" - clear the date filter
    if (relativeExpression === null) {
      onChange(null);
      setIsOpen(false);
      setCustomStart('');
      setCustomEnd('');
      setDateError(null);
      return;
    }

    const range = parseRelativeTime(relativeExpression);
    if (!range) return;

    const { start, end } = range;
    onChange({
      start: formatForBackend(start),
      end: formatForBackend(end),
      preset: relativeExpression,
    });
    setIsOpen(false);
    setCustomStart('');
    setCustomEnd('');
    setDateError(null);
  };

  // Handle custom date range Apply
  const handleCustomApply = () => {
    setDateError(null);

    if (!customStart || !customEnd) {
      setDateError('Please enter both start and end dates');
      return;
    }

    // Try parsing as relative time first, then as ISO8601
    let startDate: Date | null = null;
    let endDate: Date | null = null;

    // Parse start date
    const relativeStart = parseRelativeTime(customStart);
    if (relativeStart) {
      startDate = relativeStart.start;
    } else {
      startDate = parseISO8601(customStart);
    }

    // Parse end date
    const relativeEnd = parseRelativeTime(customEnd);
    if (relativeEnd) {
      endDate = relativeEnd.end;
    } else {
      endDate = parseISO8601(customEnd);
    }

    if (!startDate) {
      setDateError('Invalid start date format. Use YYYY-MM-DD HH:mm:ss or -7d');
      return;
    }

    if (!endDate) {
      setDateError('Invalid end date format. Use YYYY-MM-DD HH:mm:ss or now');
      return;
    }

    // Validate range
    if (!isValidDateRange(startDate, endDate)) {
      setDateError('End date must be after start date');
      return;
    }

    // Update with UTC ISO8601 strings
    onChange({
      start: formatForBackend(startDate),
      end: formatForBackend(endDate),
      preset: 'custom',
    });

    setIsOpen(false);
    setCustomStart('');
    setCustomEnd('');
    setDateError(null);
  };

  // Get display label for the button
  const displayLabel = React.useMemo(() => {
    // No date filter applied
    if (!value) return showAllTime ? 'All time' : 'Select dates';

    // If we have a preset (relative expression), generate label from it
    if (value.preset && value.preset !== 'custom') {
      return getRelativeTimeLabel(value.preset);
    }

    // For custom ranges, format the actual dates for display
    try {
      const start = parseISO8601(value.start);
      const end = parseISO8601(value.end);
      if (start && end) {
        return `${formatForDisplay(start)} - ${formatForDisplay(end)}`;
      }
    } catch {
      // Fall through to default
    }

    return 'Custom range';
  }, [value, showAllTime]);

  return (
    <DropdownMenu.Root open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenu.Trigger asChild>
        <Button
          className={className}
          variant={variant}
          size={size}
          icon={<Calendar />}
          iconRight={<ChevronDown />}
        >
          {displayLabel}
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content
        className="w-[320px] items-stretch p-0"
        side="bottom"
        align="start"
        sideOffset={4}
      >
            <Accordion
              trigger={
                <div className="flex w-full items-center justify-start gap-2 px-3 py-3">
                  <span className="grow shrink-0 basis-0 text-left text-body-bold font-body-bold text-default-font">
                    Presets
                  </span>
                  <Accordion.Chevron />
                </div>
              }
              defaultOpen={true}
            >
              <div className="flex w-full grow shrink-0 basis-0 flex-col items-start border-t border-solid border-neutral-border">
                {/* Relative time presets */}
                {presets.map((expr) => (
                  <div
                    key={expr}
                    className="flex w-full items-center gap-2 bg-neutral-50 px-3 py-2 cursor-pointer hover:bg-neutral-100"
                    onClick={() => handlePresetClick(expr)}
                  >
                    <span className="grow shrink-0 basis-0 text-body font-body text-default-font">
                      {getRelativeTimeLabel(expr)}
                    </span>
                  </div>
                ))}
                {/* All time option - clears date filter */}
                {showAllTime && (
                  <div
                    className="flex w-full items-center gap-2 bg-neutral-50 px-3 py-2 cursor-pointer hover:bg-neutral-100"
                    onClick={() => handlePresetClick(null)}
                  >
                    <span className="grow shrink-0 basis-0 text-body font-body text-default-font">
                      All time
                    </span>
                  </div>
                )}
              </div>
            </Accordion>
            <div className="flex h-px w-full flex-none flex-col items-center gap-2 bg-neutral-border" />
            <Accordion
              trigger={
                <div className="flex w-full items-center justify-start gap-2 px-3 py-3">
                  <span className="grow shrink-0 basis-0 text-left text-body-bold font-body-bold text-default-font">
                    Custom Range
                  </span>
                  <Accordion.Chevron />
                </div>
              }
            >
              <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-3 border-t border-solid border-neutral-border px-3 py-3">
                <div className="flex w-full items-start gap-2 text-caption font-caption text-subtext-color">
                  Times shown in your local timezone ({userTimezone})
                </div>
                <div className="flex w-full items-start gap-2">
                  <TextField
                    className="h-auto grow shrink-0 basis-0"
                    label="Start date"
                    helpText={dateError || ""}
                    error={!!dateError}
                  >
                    <TextField.Input
                      className="h-8 w-full flex-none"
                      type="text"
                      value={customStart}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        setCustomStart(e.target.value);
                        setDateError(null);
                      }}
                      placeholder="YYYY-MM-DD HH:mm or -7d"
                    />
                  </TextField>
                </div>
                <div className="flex w-full items-start gap-2">
                  <TextField
                    className="h-auto grow shrink-0 basis-0"
                    label="End date"
                    helpText=""
                  >
                    <TextField.Input
                      className="h-8 w-full flex-none"
                      type="text"
                      value={customEnd}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => {
                        setCustomEnd(e.target.value);
                        setDateError(null);
                      }}
                      placeholder="YYYY-MM-DD HH:mm or now"
                    />
                  </TextField>
                </div>
                <Button
                  className="h-6 w-full flex-none"
                  size="small"
                  onClick={handleCustomApply}
                  disabled={!customStart || !customEnd}
                >
                  Apply
                </Button>
              </div>
            </Accordion>
        </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
export default DateRangePicker;
