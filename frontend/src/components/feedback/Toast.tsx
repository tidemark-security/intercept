"use client";

import React from "react";

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
    return (
      <div
        className={cn(
          "group/2c7966c2 flex w-80 items-center gap-4 rounded-md border border-solid border-neutral-border bg-default-background px-4 py-3 shadow-black-shadow-medium",
          {
            "border border-solid border-success-600 shadow-md":
              variant === "success",
            "border border-solid border-accent-2-primary shadow-accent-2-shadow-medium":
              variant === "error",
            "border border-solid border-brand-primary shadow-md":
              variant === "brand",
          },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {icon ? (
          <IconWrapper
            className={cn(
              "text-heading-3 font-heading-3 text-neutral-700",
              {
                "text-success-700": variant === "success",
                "text-error-700": variant === "error",
                "text-brand-600": variant === "brand",
              }
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
                {
                  "text-success-700": variant === "success",
                  "text-error-700": variant === "error",
                  "text-brand-primary": variant === "brand",
                }
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
