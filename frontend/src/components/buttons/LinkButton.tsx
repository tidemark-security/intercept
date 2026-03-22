"use client";

import React from "react";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";

interface LinkButtonRootProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  disabled?: boolean;
  variant?: "brand" | "neutral" | "inverse";
  size?: "large" | "medium" | "small";
  icon?: React.ReactNode;
  children?: React.ReactNode;
  iconRight?: React.ReactNode;
  onClick?: (event: React.MouseEvent<HTMLButtonElement>) => void;
  className?: string;
}

const LinkButtonRoot = React.forwardRef<HTMLButtonElement, LinkButtonRootProps>(
  function LinkButtonRoot(
    {
      disabled = false,
      variant = "neutral",
      size = "medium",
      icon = null,
      children,
      iconRight = null,
      className,
      type = "button",
      ...otherProps
    }: LinkButtonRootProps,
    ref
  ) {
    return (
      <button
        className={cn(
          "group/a4ee726a flex cursor-pointer items-center gap-1 border-none bg-transparent",
          { "flex-row flex-nowrap gap-1": size === "large" },
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
              "text-body font-body text-neutral-700 group-hover/a4ee726a:text-brand-700 group-disabled/a4ee726a:text-neutral-400 group-hover/a4ee726a:group-disabled/a4ee726a:text-neutral-400",
              {
                "text-caption font-caption": size === "small",
                "text-heading-3 font-heading-3": size === "large",
                "text-black group-hover/a4ee726a:text-black":
                  variant === "inverse",
                "text-brand-700 group-hover/a4ee726a:text-brand-700":
                  variant === "brand",
              }
            )}
          >
            {icon}
          </IconWrapper>
        ) : null}
        {children ? (
          <span
            className={cn(
              "text-body font-body text-neutral-700 group-hover/a4ee726a:text-brand-700 group-hover/a4ee726a:underline group-disabled/a4ee726a:text-neutral-400 group-hover/a4ee726a:group-disabled/a4ee726a:text-neutral-400 group-hover/a4ee726a:group-disabled/a4ee726a:no-underline",
              {
                "text-caption font-caption": size === "small",
                "text-heading-3 font-heading-3": size === "large",
                "text-black group-hover/a4ee726a:text-black":
                  variant === "inverse",
                "text-brand-700 group-hover/a4ee726a:text-brand-700":
                  variant === "brand",
              }
            )}
          >
            {children}
          </span>
        ) : null}
        {iconRight ? (
          <IconWrapper
            className={cn(
              "text-body font-body text-neutral-700 group-hover/a4ee726a:text-brand-700 group-disabled/a4ee726a:text-neutral-400 group-hover/a4ee726a:group-disabled/a4ee726a:text-neutral-400",
              {
                "text-caption font-caption": size === "small",
                "text-heading-3 font-heading-3": size === "large",
                "text-black group-hover/a4ee726a:text-black":
                  variant === "inverse",
                "text-brand-700 group-hover/a4ee726a:text-brand-700":
                  variant === "brand",
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

export const LinkButton = LinkButtonRoot;
