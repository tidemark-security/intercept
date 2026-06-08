"use client";

import React from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/utils/cn";

export interface ToolbarButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "value"> {
  icon: React.ReactNode;
  label: React.ReactNode;
  value: React.ReactNode;
  chevron?: boolean;
  active?: boolean;
  className?: string;
}

export const ToolbarButton = React.forwardRef<
  HTMLButtonElement,
  ToolbarButtonProps
>(function ToolbarButton(
  {
    icon,
    label,
    value,
    chevron = false,
    active = false,
    className,
    type = "button",
    ...buttonProps
  },
  ref,
) {
  const accessibleName =
    buttonProps["aria-label"] ??
    [label, value].filter(Boolean).join(" ");

  return (
    <button
      className={cn(
        "group flex h-12 min-w-0 items-center gap-2 rounded-none border-0 px-2 text-left transition-colors",
        "bg-default-background hover:bg-neutral-100 focus-visible:outline focus-visible:outline-1 focus-visible:outline-focus-border",
        active && "bg-brand-primary/10",
        className,
      )}
      ref={ref}
      type={type}
      aria-label={accessibleName}
      {...buttonProps}
    >
      <span className="flex shrink-0 items-center justify-center text-body font-body text-subtext-color group-hover:text-default-font">
        {icon}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-caption font-caption text-subtext-color">
          {label}
        </span>
        <span className="truncate text-caption-bold font-caption-bold text-default-font">
          {value}
        </span>
      </span>
      {chevron ? (
        <ChevronDown className="shrink-0 text-caption font-caption text-subtext-color" />
      ) : null}
    </button>
  );
});
