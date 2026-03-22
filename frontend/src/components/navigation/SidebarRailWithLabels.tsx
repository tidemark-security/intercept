
"use client";

import React from "react";

import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { Tooltip } from "@/components/overlays/Tooltip";

import { CircleDashed } from 'lucide-react';
interface NavItemProps extends React.HTMLAttributes<HTMLDivElement> {
  icon?: React.ReactNode;
  children?: React.ReactNode;
  selected?: boolean;
  mobile?: boolean;
  className?: string;
}

const NavItem = React.forwardRef<HTMLDivElement, NavItemProps>(function NavItem(
  {
    icon = <CircleDashed />,
    children,
    selected = false,
    mobile = false,
    className,
    ...otherProps
  }: NavItemProps,
  ref
) {
  return (
    <Tooltip.Provider>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <div
            className={cn(
              "group/8815d632 flex h-12 w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-md p-2",
              { "h-12 w-12 flex-col flex-nowrap gap-0 px-1 py-1": mobile },
              className
            )}
            ref={ref}
            {...otherProps}
          >
            {icon ? (
              <IconWrapper
                className={cn(
                  "text-heading-2 font-heading-2 text-brand-primary group-hover/8815d632:text-brand-200 group-active/8815d632:text-brand-200",
                  {
                    "text-accent-1-400 group-hover/8815d632:text-accent-1-400":
                      selected,
                  }
                )}
              >
                {icon}
              </IconWrapper>
            ) : null}
          </div>
        </Tooltip.Trigger>
        <Tooltip.Content
          side="right"
          align="center"
          sideOffset={4}
          className="z-[9999]"
        >
          {children}
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
});

interface SidebarRailWithLabelsRootProps
  extends React.HTMLAttributes<HTMLElement> {
  header?: React.ReactNode;
  footer?: React.ReactNode;
  children?: React.ReactNode;
  mobile?: boolean;
  className?: string;
}

const SidebarRailWithLabelsRoot = React.forwardRef<
  HTMLElement,
  SidebarRailWithLabelsRootProps
>(function SidebarRailWithLabelsRoot(
  {
    header,
    footer,
    children,
    mobile = false,
    className,
    ...otherProps
  }: SidebarRailWithLabelsRootProps,
  ref
) {
  return (
    <nav
      className={cn(
        "group/3296372a flex h-full w-16 flex-col items-center justify-between bg-black",
        {
          "h-auto w-full flex-row flex-nowrap justify-between border-t border-solid border-brand-primary px-1 py-1":
            mobile,
        },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {header ? (
        <div
          className={cn(
            "flex flex-col items-center justify-center p-2",
            { hidden: mobile }
          )}
        >
          {header}
        </div>
      ) : null}
      {children ? (
        <div
          className={cn(
            "flex w-full grow shrink-0 basis-0 flex-col items-center gap-1 px-2 py-2 overflow-auto",
            {
              "flex h-auto grow shrink-0 basis-0 flex-row flex-nowrap items-center justify-between self-stretch px-0 py-0":
                mobile,
            }
          )}
        >
          {children}
        </div>
      ) : null}
      {footer ? (
        <div
          className={cn(
            "flex flex-col items-center justify-end gap-1 overflow-hidden px-2 py-2",
            { hidden: mobile }
          )}
        >
          {footer}
        </div>
      ) : null}
    </nav>
  );
});

export const SidebarRailWithLabels = Object.assign(SidebarRailWithLabelsRoot, {
  NavItem,
});