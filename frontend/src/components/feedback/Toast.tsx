"use client";

import React from "react";

import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";

import { Info } from 'lucide-react';
interface ToastRootProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  variant?: "brand" | "neutral" | "error" | "success";
  icon?: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

const ToastRoot = React.forwardRef<HTMLDivElement, ToastRootProps>(
  function ToastRoot(
    {
      variant = "neutral",
      icon = <Info />,
      title,
      description,
      actions,
      className,
      ...otherProps
    }: ToastRootProps,
    ref
  ) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";

    return (
      <div
        className={cn(
          "group/2c7966c2 flex w-80 items-center gap-4 rounded-md border border-solid border-neutral-border bg-default-background px-4 py-3 shadow-black-shadow-medium",
          variant === "success" &&
            (isDarkTheme
              ? "border border-solid border-success-600 shadow-md"
              : "border border-solid border-success-800 shadow-md"),
          variant === "error" &&
            (isDarkTheme
              ? "border border-solid border-error-500 shadow-accent-2-shadow-medium"
              : "border border-solid border-error-700 shadow-accent-2-shadow-medium"),
          variant === "brand" &&
            (isDarkTheme
              ? "border border-solid border-brand-primary shadow-md"
              : "border border-solid border-back shadow-black-shadow-medium"),
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {icon ? (
          <IconWrapper
            className={cn(
              "text-heading-3 font-heading-3 text-neutral-700",
              variant === "success" && (isDarkTheme ? "text-success-700" : "text-success-900"),
              variant === "error" && (isDarkTheme ? "text-error-700" : "text-error-900"),
              variant === "brand" && (isDarkTheme ? "text-brand-600" : "text-black")
            )}
          >
            {icon}
          </IconWrapper>
        ) : null}
        <div className="flex grow shrink-0 basis-0 flex-col items-start">
          {title ? (
            <span
              className={cn(
                "w-full text-body-bold font-body-bold text-default-font",
                variant === "success" && (isDarkTheme ? "text-success-700" : "text-success-900"),
                variant === "error" && (isDarkTheme ? "text-error-700" : "text-error-900"),
                variant === "brand" && (isDarkTheme ? "text-brand-600" : "text-black")
              )}
            >
              {title}
            </span>
          ) : null}
          {description ? (
            <span className="w-full text-caption font-caption text-subtext-color">
              {description}
            </span>
          ) : null}
        </div>
        {actions ? (
          <div className="flex items-center justify-end gap-1">{actions}</div>
        ) : null}
      </div>
    );
  }
);

export const Toast = ToastRoot;
