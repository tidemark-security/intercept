"use client";
/**
 * Switch Component
 * 
 * A toggle switch built on Radix UI primitives.
 */

import React from "react";
import * as RadixSwitch from "@radix-ui/react-switch";
import { cn } from "@/utils/cn";

interface ThumbProps extends React.ComponentPropsWithoutRef<typeof RadixSwitch.Thumb> {
  className?: string;
}

const Thumb = React.forwardRef<HTMLSpanElement, ThumbProps>(function Thumb(
  { className, ...otherProps }: ThumbProps,
  ref
) {
  return (
    <RadixSwitch.Thumb
      className={cn(
        "flex h-3.5 w-3.5 flex-col items-start gap-2 rounded-full bg-black shadow-sm",
        "data-[state=checked]:translate-x-3 transition-transform",
        className
      )}
      ref={ref}
      {...otherProps}
    />
  );
});

interface SwitchRootProps extends React.ComponentPropsWithoutRef<typeof RadixSwitch.Root> {
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  className?: string;
}

const SwitchRoot = React.forwardRef<HTMLButtonElement, SwitchRootProps>(
  function SwitchRoot(
    { checked = false, className, ...otherProps }: SwitchRootProps,
    ref
  ) {
    return (
      <RadixSwitch.Root
        checked={checked}
        className={cn(
          "group/7a464794 flex h-5 w-8 cursor-pointer flex-col items-start justify-center gap-2 rounded-full border border-solid border-neutral-200 bg-neutral-200 px-0.5 py-0.5",
          "data-[state=checked]:border data-[state=checked]:border-solid data-[state=checked]:border-brand-600 data-[state=checked]:bg-brand-600",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <Thumb />
      </RadixSwitch.Root>
    );
  }
);

export const Switch = Object.assign(SwitchRoot, {
  Thumb,
});
