"use client";

import React from "react";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";

interface BadgeRootProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "brand" | "neutral" | "error" | "warning" | "success";
  icon?: React.ReactNode;
  children?: React.ReactNode;
  iconRight?: React.ReactNode;
  compact?: boolean;
  className?: string;
}

const BadgeRoot = React.forwardRef<HTMLDivElement, BadgeRootProps>(
  function BadgeRoot(
    {
      variant = "brand",
      icon = null,
      children,
      iconRight = null,
      compact = false,
      className,
      ...otherProps
    }: BadgeRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "group/97bdb082 flex h-6 items-center justify-center gap-1 rounded-md border border-solid border-neutral-border bg-brand-50 px-2",
          {
            "border border-solid border-success-100 bg-success-100":
              variant === "success",
            "border border-solid border-warning-100 bg-warning-100":
              variant === "warning",
            "border border-solid border-error-100 bg-error-100":
              variant === "error",
            "border border-solid border-neutral-200 bg-neutral-200":
              variant === "neutral",
          },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {icon ? (
          <IconWrapper
            className={cn(
              "text-caption font-caption text-brand-800",
              {
                "text-success-900": variant === "success",
                "text-warning-900": variant === "warning",
                "text-error-800": variant === "error",
                "text-neutral-700": variant === "neutral",
              }
            )}
          >
            {icon}
          </IconWrapper>
        ) : null}
        {children ? (
          <span
            className={cn(
              "line-clamp-1 grow shrink-0 basis-0 text-caption font-caption text-brand-800 text-center text-ellipsis overflow-hidden",
              {
                hidden: compact,
                "text-success-900": variant === "success",
                "text-warning-900": variant === "warning",
                "text-error-800": variant === "error",
                "text-neutral-700": variant === "neutral",
              }
            )}
          >
            {children}
          </span>
        ) : null}
        {iconRight ? (
          <IconWrapper
            className={cn(
              "text-caption font-caption text-brand-700",
              {
                "text-success-800": variant === "success",
                "text-warning-800": variant === "warning",
                "text-error-700": variant === "error",
                "text-neutral-700": variant === "neutral",
              }
            )}
          >
            {iconRight}
          </IconWrapper>
        ) : null}
      </div>
    );
  }
);

export const Badge = BadgeRoot;
