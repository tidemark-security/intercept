"use client";
/*
 * Calendar Component
 * Uses react-day-picker for date selection
 */

import React from "react";
import { DayPicker, type DateRange, type Matcher } from "react-day-picker";
import { cn } from "@/utils/cn";
import { ChevronLeft, ChevronRight } from "lucide-react";

export interface CalendarProps {
  className?: string;
  mode?: "single" | "range" | "multiple";
  selected?: Date | Date[] | DateRange;
  onSelect?: (date: Date | Date[] | DateRange | undefined) => void;
  disabled?: boolean;
  disablePast?: boolean;
  disableFuture?: boolean;
  fromDate?: Date;
  toDate?: Date;
  defaultMonth?: Date;
}

const Calendar = React.forwardRef<HTMLDivElement, CalendarProps>(
  function Calendar(
    {
      className,
      mode = "single",
      selected,
      onSelect,
      disabled = false,
      disablePast = false,
      disableFuture = false,
      fromDate,
      toDate,
      defaultMonth,
      ...props
    }: CalendarProps,
    ref
  ) {
    const today = new Date();
    
    // Build disabled dates configuration
    const disabledDates: Matcher[] = [];
    if (disablePast) {
      disabledDates.push((date: Date) => date < today);
    }
    if (disableFuture) {
      disabledDates.push((date: Date) => date > today);
    }

    return (
      <div ref={ref} className={cn("relative", className)}>
        <DayPicker
          mode={mode as any}
          selected={selected as any}
          onSelect={onSelect as any}
          disabled={disabled ? true : disabledDates.length > 0 ? disabledDates : undefined}
          fromDate={fromDate}
          toDate={toDate}
          defaultMonth={defaultMonth}
          showOutsideDays
          classNames={{
            root: "relative",
            month: "flex flex-col gap-4",
            months: "relative flex flex-wrap max-w-fit gap-4",
            nav: "absolute flex items-center justify-between h-8 w-full p-0.5",
            month_caption: "flex items-center justify-center h-8",
            caption_label: "text-body-bold font-body-bold text-default-font",
            button_previous:
              "inline-flex items-center justify-center h-8 w-8 bg-transparent rounded border-none hover:bg-neutral-50 active:bg-neutral-100",
            button_next:
              "inline-flex items-center justify-center h-8 w-8 bg-transparent rounded border-none hover:bg-neutral-50 active:bg-neutral-100",
            chevron: "text-[18px] font-[500] leading-[18px] text-neutral-600",
            weeks: "flex flex-col gap-2",
            weekdays: "flex pb-4",
            weekday: "w-8 text-caption-bold font-caption-bold text-subtext-color text-center",
            week: "flex rounded-lg overflow-hidden",
            day: "group flex p-0 cursor-pointer items-center justify-center text-body font-body text-default-font h-8 w-8",
            day_button:
              "flex h-8 w-8 cursor-pointer items-center justify-center gap-2 rounded-lg border-none hover:bg-neutral-100",
            selected: "bg-brand-600 text-white rounded-lg",
            today: "font-bold",
            outside: "text-neutral-400 opacity-50",
            disabled: "text-neutral-300 cursor-not-allowed",
            range_start: "bg-brand-600 text-white rounded-l-lg rounded-r-none",
            range_middle: "bg-neutral-100 text-default-font rounded-none",
            range_end: "bg-brand-600 text-white rounded-r-lg rounded-l-none",
          }}
          components={{
            Chevron: ({ orientation }) =>
              orientation === "left" ? (
                <ChevronLeft className="h-4 w-4 text-neutral-600" />
              ) : (
                <ChevronRight className="h-4 w-4 text-neutral-600" />
              ),
          }}
          {...props}
        />
      </div>
    );
  }
);

export { Calendar };
