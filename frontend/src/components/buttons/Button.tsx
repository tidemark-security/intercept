"use client";
/**
 * Button Component
 * 
 * A styled button with multiple variants and loading state.
 */

import React from "react";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { Loader } from "@/components/feedback/Loader";

interface ButtonRootProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  disabled?: boolean;
  variant?:
    | "brand-primary"
    | "brand-secondary"
    | "brand-tertiary"
    | "neutral-primary"
    | "neutral-secondary"
    | "neutral-tertiary"
    | "destructive-primary"
    | "destructive-secondary"
    | "destructive-tertiary"
    | "inverse";
  size?: "large" | "medium" | "small";
  children?: React.ReactNode;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  loading?: boolean;
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  className?: string;
}

const ButtonRoot = React.forwardRef<HTMLButtonElement, ButtonRootProps>(
  function ButtonRoot(
    {
      disabled = false,
      variant = "brand-primary",
      size = "medium",
      children,
      icon = null,
      iconRight = null,
      loading = false,
      className,
      type = "button",
      ...otherProps
    }: ButtonRootProps,
    ref
  ) {
    return (
      <button
        className={cn(
          "group/3b777358 flex h-8 cursor-pointer items-center justify-center gap-2 rounded-md border-none bg-brand-primary px-3 hover:bg-brand-300 active:bg-brand-600 disabled:cursor-default disabled:bg-neutral-200 hover:disabled:cursor-default hover:disabled:bg-neutral-200 active:disabled:cursor-default active:disabled:bg-neutral-200",
          {
            "h-6 w-auto flex-row flex-nowrap gap-1 px-2 py-0": size === "small",
            "h-10 w-auto px-4 py-0": size === "large",
            "bg-transparent hover:bg-[#ffffff29] active:bg-[#ffffff3d]":
              variant === "inverse",
            "bg-transparent hover:bg-error-50 active:bg-error-100":
              variant === "destructive-tertiary",
            "border border-solid border-neutral-border bg-default-background hover:bg-error-1200 active:bg-default-background":
              variant === "destructive-secondary",
            "bg-error-600 hover:bg-error-500 active:bg-error-600":
              variant === "destructive-primary",
            "bg-transparent hover:bg-neutral-100 active:bg-neutral-200":
              variant === "neutral-tertiary",
            "border border-solid border-neutral-border bg-default-background hover:bg-neutral-50 active:bg-default-background":
              variant === "neutral-secondary",
            "bg-neutral-100 hover:bg-neutral-200 active:bg-neutral-100":
              variant === "neutral-primary",
            "bg-transparent hover:bg-brand-50 active:bg-brand-100":
              variant === "brand-tertiary",
            "border border-solid border-brand-primary bg-default-background hover:bg-brand-1100 active:bg-default-background":
              variant === "brand-secondary",
          },
          className
        )}
        ref={ref}
        type={type}
        disabled={disabled}
        {...otherProps}
      >
        {icon ? (
          <IconWrapper
            className={cn(
              "text-body font-body text-black group-disabled/3b777358:text-neutral-400",
              {
                hidden: loading,
                "text-body font-body": size === "small",
                "text-heading-3 font-heading-3": size === "large",
                "text-black": variant === "inverse",
                "text-error-700":
                  variant === "destructive-tertiary" ||
                  variant === "destructive-secondary",
                "text-neutral-700":
                  variant === "neutral-tertiary" ||
                  variant === "neutral-secondary" ||
                  variant === "neutral-primary",
                "text-brand-700":
                  variant === "brand-tertiary" || variant === "brand-secondary",
              }
            )}
          >
            {icon}
          </IconWrapper>
        ) : null}
        <div
          className={cn(
            "hidden h-4 w-4 flex-none items-center justify-center gap-2",
            { flex: loading, "h-3 w-3 flex-none": size === "small" }
          )}
        >
          <Loader
            size="small"
            className={cn(
              "text-caption font-caption text-black group-disabled/3b777358:text-neutral-400",
              {
                "inline-block font-['Inter'] text-[12px] font-[400] leading-[20px] tracking-normal":
                  loading,
                "text-caption font-caption": size === "small",
                "text-error-700":
                  variant === "destructive-tertiary" ||
                  variant === "destructive-secondary",
                "text-neutral-700":
                  variant === "neutral-tertiary" ||
                  variant === "neutral-secondary" ||
                  variant === "neutral-primary",
                "text-brand-700":
                  variant === "brand-tertiary" || variant === "brand-secondary",
              }
            )}
          />
        </div>
        {children ? (
          <span
            className={cn(
              "whitespace-nowrap text-body-bold font-body-bold text-black group-disabled/3b777358:text-neutral-400",
              {
                hidden: loading,
                "text-caption-bold font-caption-bold": size === "small",
                "text-body-bold font-body-bold": size === "large",
                "text-black": variant === "inverse",
                "text-error-700": variant === "destructive-tertiary",
                "text-error-600": variant === "destructive-secondary",
                "text-neutral-700":
                  variant === "neutral-tertiary" ||
                  variant === "neutral-secondary" ||
                  variant === "neutral-primary",
                "text-brand-700": variant === "brand-tertiary",
                "text-brand-600": variant === "brand-secondary",
              }
            )}
          >
            {children}
          </span>
        ) : null}
        {iconRight ? (
          <IconWrapper
            className={cn(
              "text-body font-body text-black group-disabled/3b777358:text-neutral-400",
              {
                "text-body font-body": size === "small",
                "text-heading-3 font-heading-3": size === "large",
                "text-black": variant === "inverse",
                "text-error-700":
                  variant === "destructive-tertiary" ||
                  variant === "destructive-secondary",
                "text-neutral-700":
                  variant === "neutral-tertiary" ||
                  variant === "neutral-secondary" ||
                  variant === "neutral-primary",
                "text-brand-700":
                  variant === "brand-tertiary" || variant === "brand-secondary",
              }
            )}
          >
            {iconRight}
          </IconWrapper>
        ) : null}
      </button>
    );
  }
);

export const Button = ButtonRoot;
