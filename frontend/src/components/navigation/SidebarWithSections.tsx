"use client";

import React from "react";

import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";

import { CircleDashed } from 'lucide-react';
interface NavItemProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: React.ReactNode;
  children?: React.ReactNode;
  selected?: boolean;
  rightSlot?: React.ReactNode;
  className?: string;
}

const NavItem = React.forwardRef<HTMLDivElement, NavItemProps>(function NavItem(
  {
    icon = <CircleDashed />,
    children,
    selected = false,
    rightSlot,
    className,
    ...otherProps
  }: NavItemProps,
  ref
) {
  return (
    <div
      className={cn(
        "group/2713e17b flex w-full cursor-pointer items-center gap-2 rounded-md px-3 py-2 hover:bg-neutral-50 active:bg-neutral-100",
        { "bg-brand-50 hover:bg-brand-50 active:bg-brand-100": selected },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {icon ? (
        <IconWrapper
          className={cn(
            "text-heading-3 font-heading-3 text-neutral-600",
            { "text-brand-700": selected }
          )}
        >
          {icon}
        </IconWrapper>
      ) : null}
      {children ? (
        <span
          className={cn(
            "line-clamp-1 grow shrink-0 basis-0 text-body-bold font-body-bold text-neutral-600",
            { "text-brand-700": selected }
          )}
        >
          {children}
        </span>
      ) : null}
      {rightSlot ? <div className="flex items-center">{rightSlot}</div> : null}
    </div>
  );
});

interface NavSectionProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  label?: React.ReactNode;
  className?: string;
}

const NavSection = React.forwardRef<HTMLDivElement, NavSectionProps>(
  function NavSection(
    { children, label, className, ...otherProps }: NavSectionProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "flex w-full flex-col items-start gap-1 pt-6",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <div className="flex w-full flex-col items-start gap-4 px-3 py-1">
          {label ? (
            <span className="w-full text-caption-bold font-caption-bold text-subtext-color">
              {label}
            </span>
          ) : null}
        </div>
        {children ? (
          <div className="flex w-full grow shrink-0 basis-0 flex-col items-start gap-1">
            {children}
          </div>
        ) : null}
      </div>
    );
  }
);

interface SidebarWithSectionsRootProps
  extends React.HTMLAttributes<HTMLElement> {
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  className?: string;
}

const SidebarWithSectionsRoot = React.forwardRef<
  HTMLElement,
  SidebarWithSectionsRootProps
>(function SidebarWithSectionsRoot(
  {
    header,
    footer,
    children,
    className,
    ...otherProps
  }: SidebarWithSectionsRootProps,
  ref
) {
  return (
    <nav
      className={cn(
        "flex h-full w-60 flex-col items-start border-r border-solid border-neutral-border bg-default-background",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {header ? (
        <div className="flex w-full flex-col items-start gap-2 px-6 py-6">
          {header}
        </div>
      ) : null}
      {children ? (
        <div className="flex w-full grow shrink-0 basis-0 flex-col items-start px-4 py-4 overflow-auto">
          {children}
        </div>
      ) : null}
      {footer ? (
        <div className="flex w-full items-center gap-4 border-t border-solid border-neutral-border px-6 py-6">
          {footer}
        </div>
      ) : null}
    </nav>
  );
});

export const SidebarWithSections = Object.assign(SidebarWithSectionsRoot, {
  NavItem,
  NavSection,
});
