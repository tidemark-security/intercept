"use client";

import React from "react";

import { cn } from "@/utils/cn";

export type MenuCardBaseVariant = "default" | "selected";

interface MenuCardBaseProps extends React.HTMLAttributes<HTMLDivElement> {
  isDarkTheme: boolean;
  variant?: MenuCardBaseVariant;
}

const MENU_CARD_GROUP_CLASS = "group/6c3f1f95";

export function getMenuCardTitleClassName(
  isDarkTheme: boolean,
  variant: MenuCardBaseVariant,
  className?: string
): string {
  return cn(
    "line-clamp-1 min-w-[240px] grow shrink-0 basis-0 text-body-bold font-body-bold",
    {
      "text-[#fafafaff] group-hover/6c3f1f95:text-brand-400": isDarkTheme,
      "text-default-font": !isDarkTheme,
      "text-accent-1-400": variant === "selected" && isDarkTheme,
    },
    className
  );
}

export function getMenuCardMetaClassName(
  isDarkTheme: boolean,
  variant: MenuCardBaseVariant,
  className?: string
): string {
  return cn(
    "text-caption font-caption text-subtext-color",
    {
      "group-hover/6c3f1f95:text-brand-700": isDarkTheme,
      "text-accent-1-700": variant === "selected" && isDarkTheme,
    },
    className
  );
}

export const MenuCardBase = React.forwardRef<HTMLDivElement, MenuCardBaseProps>(
  function MenuCardBase(
    { isDarkTheme, variant = "default", className, children, ...otherProps },
    ref
  ) {
    return (
      <div
        className={cn(
          `${MENU_CARD_GROUP_CLASS} flex w-full cursor-pointer flex-col flex-wrap items-center justify-between rounded-sm border border-solid border-neutral-border bg-neutral-0 px-4 py-3`,
          {
            "hover:border hover:border-solid hover:border-brand-primary": isDarkTheme,
            "hover:bg-brand-primary hover:border-brand-700": !isDarkTheme,
            "border border-solid border-accent-1-primary":
              variant === "selected" && isDarkTheme,
            "bg-neutral-300 border-neutral-900": variant === "selected" && !isDarkTheme,
          },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {children}
      </div>
    );
  }
);
