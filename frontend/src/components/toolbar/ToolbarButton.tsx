"use client";

import React from "react";
import { ChevronDown } from "lucide-react";

import { useTheme } from "@/contexts/ThemeContext";
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
  const { resolvedTheme } = useTheme();
  const accessibleName =
    buttonProps["aria-label"] ??
    [label, value].filter(Boolean).join(" ");

  return (
    <button
      className={cn(
        "group relative flex h-12 min-w-0 items-center gap-2 rounded-none border-0 px-2 text-left transition-colors",
        "bg-default-background focus-visible:outline focus-visible:outline-1 focus-visible:outline-focus-border",
        resolvedTheme === "light" ? "hover:bg-neutral-200" : "hover:bg-neutral-100",
        className,
      )}
      ref={ref}
      type={type}
      aria-label={accessibleName}
      {...buttonProps}
    >
      {active ? (
        <span
          aria-hidden="true"
          data-modified-indicator="true"
          className={cn(
            "absolute right-2.5 top-1.5 h-2 w-2 rounded-full",
            resolvedTheme === "light" ? "bg-default-font" : "bg-brand-primary",
          )}
        />
      ) : null}
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
