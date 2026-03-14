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
        "relative z-10 h-4 w-4 bg-black",
        "data-[state=checked]:translate-x-6 transition-transform",
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
          "group/7a464794 relative inline-flex h-6 w-12 cursor-pointer items-center border border-solid border-neutral-300 bg-neutral-200 px-1 py-1",
          "data-[state=checked]:border data-[state=checked]:border-solid data-[state=checked]:border-brand-primary data-[state=checked]:bg-brand-500",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute left-2 text-[10px] font-semibold leading-none transition-colors",
            checked ? "text-black/75" : "text-transparent"
          )}
        >
          O
        </span>
        <span
          aria-hidden="true"
          className={cn(
            "pointer-events-none absolute right-2 text-[10px] font-semibold leading-none transition-colors",
            checked ? "text-transparent" : "text-neutral-1000/75"
          )}
        >
          I
        </span>
        <Thumb />
      </RadixSwitch.Root>
    );
  }
);

export const Switch = Object.assign(SwitchRoot, {
  Thumb,
});
