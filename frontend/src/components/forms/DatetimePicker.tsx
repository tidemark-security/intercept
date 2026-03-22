"use client";

import React from "react";
import { cn } from "@/utils/cn";
import { TextField } from "./TextField";

interface DatetimePickerRootProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

const DatetimePickerRoot = React.forwardRef<
  HTMLDivElement,
  DatetimePickerRootProps
>(function DatetimePickerRoot(
  { className, ...otherProps }: DatetimePickerRootProps,
  ref
) {
  return (
    <div
      className={cn(
        "flex w-48 items-center gap-2",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <TextField className="h-auto w-28 flex-none" label="" helpText="">
        <TextField.Input placeholder="2024-01-15" />
      </TextField>
      <TextField label="" helpText="">
        <TextField.Input placeholder="14:30" />
      </TextField>
    </div>
  );
});

export const DatetimePicker = DatetimePickerRoot;
