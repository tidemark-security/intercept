
"use client";
/**
 * Dropdown Menu Component
 * 
 * A dropdown menu built on Radix UI primitives with proper z-index layering.
 * Uses PortalContainerContext to render inside modals when appropriate.
 * 
 * Exports both compound components (DropdownMenu) and Radix primitives for inline usage.
 */

import React from "react";
import { Link } from "@/components/navigation/Link";
import * as RadixDropdownMenu from "@radix-ui/react-dropdown-menu";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { usePortalContainer } from "@/contexts/PortalContainerContext";
import { useTheme } from "@/contexts/ThemeContext";

import { Star } from 'lucide-react';

export const DropdownMenuRoot = RadixDropdownMenu.Root;
export const DropdownMenuTrigger = RadixDropdownMenu.Trigger;
export const DropdownMenuPortal = RadixDropdownMenu.Portal;
export const DropdownMenuSub = RadixDropdownMenu.Sub;
export const DropdownMenuSubTrigger = RadixDropdownMenu.SubTrigger;
export const DropdownMenuSubContent = RadixDropdownMenu.SubContent;
export const DropdownMenuRadioGroup = RadixDropdownMenu.RadioGroup;
export const DropdownMenuRadioItem = RadixDropdownMenu.RadioItem;
export const DropdownMenuCheckboxItem = RadixDropdownMenu.CheckboxItem;
export const DropdownMenuItemIndicator = RadixDropdownMenu.ItemIndicator;
export const DropdownMenuSeparator = RadixDropdownMenu.Separator;
export const DropdownMenuLabel = RadixDropdownMenu.Label;
export const DropdownMenuGroup = RadixDropdownMenu.Group;
export const DropdownMenuArrow = RadixDropdownMenu.Arrow;

// Portal-aware Content wrapper
interface DropdownMenuContentProps extends React.ComponentPropsWithoutRef<typeof RadixDropdownMenu.Content> {
  children?: React.ReactNode;
  className?: string;
}

export const DropdownMenuContent = React.forwardRef<HTMLDivElement, DropdownMenuContentProps>(
  function DropdownMenuContent({ children, className, sideOffset = 4, ...otherProps }, ref) {
    const portalContainer = usePortalContainer();
    
    return (
      <RadixDropdownMenu.Portal container={portalContainer}>
        <RadixDropdownMenu.Content
          className={cn(
            "flex min-w-[192px] flex-col items-start rounded-md border border-solid border-neutral-border bg-default-background px-1 py-1 shadow-lg",
            "z-[var(--z-popover)]",
            // Animations
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
            "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
            "data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2",
            "data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
            className
          )}
          sideOffset={sideOffset}
          ref={ref}
          {...otherProps}
        >
          {children}
        </RadixDropdownMenu.Content>
      </RadixDropdownMenu.Portal>
    );
  }
);

// Styled Item for compatibility with existing usage
interface DropdownItemProps extends React.ComponentPropsWithoutRef<typeof RadixDropdownMenu.Item> {
  icon?: React.ReactNode;
  hint?: React.ReactNode;
  showHint?: boolean;
  label?: React.ReactNode;
  to?: string;
  className?: string;
}

const DropdownItem = React.forwardRef<HTMLDivElement, DropdownItemProps>(
  function DropdownItem(
    {
      icon = <Star />,
      hint,
      showHint = false,
      label,
      to,
      className,
      ...otherProps
    }: DropdownItemProps,
    ref
  ) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";

    const content = (
      <div
        className={cn(
          "group/adcae8d6 flex w-full cursor-pointer items-center gap-2 outline-none",
          className
        )}
        ref={ref}
      >
        <div className="flex grow shrink-0 basis-0 flex-col items-start gap-1">
          <div
            className={cn(
              "flex h-8 w-full flex-none items-center gap-2 rounded-md px-3",
              "group-active/adcae8d6:bg-neutral-50",
              isDarkTheme
                ? "group-hover/adcae8d6:bg-neutral-100 group-focus/adcae8d6:bg-neutral-100 group-data-[highlighted]/adcae8d6:bg-neutral-100"
                : "group-hover/adcae8d6:bg-brand-primary group-focus/adcae8d6:bg-brand-primary group-data-[highlighted]/adcae8d6:bg-brand-primary",
              { "flex-row flex-nowrap gap-4 pl-3 pr-1 py-0": showHint }
            )}
          >
            {icon ? (
              <IconWrapper className="text-body font-body text-default-font">
                {icon}
              </IconWrapper>
            ) : null}
            {label ? (
              <span className="line-clamp-1 grow shrink-0 basis-0 text-body font-body text-default-font group-hover/adcae8d6:text-default-font">
                {label}
              </span>
            ) : null}
            <div className="flex items-center gap-2 pl-1">
              <DropdownMenu.HintBadge
                className={cn("hidden", {
                  flex: showHint,
                })}
                text={hint}
              />
            </div>
          </div>
        </div>
      </div>
    );

    return (
      <RadixDropdownMenu.Item asChild {...otherProps}>
        {to ? <Link to={to}>{content}</Link> : content}
      </RadixDropdownMenu.Item>
    );
  }
);

interface DropdownDividerProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

const DropdownDivider = React.forwardRef<HTMLDivElement, DropdownDividerProps>(
  function DropdownDivider(
    { className, ...otherProps }: DropdownDividerProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "flex w-full items-start gap-2 px-1 py-1",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <div className="flex h-px grow shrink-0 basis-0 flex-col items-center gap-2 bg-neutral-200" />
      </div>
    );
  }
);

interface HintBadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  text?: React.ReactNode;
  className?: string;
}

const HintBadge = React.forwardRef<HTMLDivElement, HintBadgeProps>(
  function HintBadge({ text, className, ...otherProps }: HintBadgeProps, ref) {
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";

    return (
      <div
        className={cn(
          "flex flex-col items-start gap-4 rounded-md px-1 py-1",
          isDarkTheme ? "bg-neutral-100" : "bg-neutral-800",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {text ? (
          <span className="font-['Kode_Mono'] text-[13px] font-[400] leading-[16px] text-accent-1-primary">
            {text}
          </span>
        ) : null}
      </div>
    );
  }
);

interface DropdownMenuRootProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

const DropdownMenuRootStyled = React.forwardRef<
  HTMLDivElement,
  DropdownMenuRootProps
>(function DropdownMenuRootStyled(
  { children, className, ...otherProps }: DropdownMenuRootProps,
  ref
) {
  return children ? (
    <div
      className={cn(
        "flex min-w-[192px] flex-col items-start rounded-md border border-solid border-neutral-border bg-default-background px-1 py-1 shadow-lg z-[var(--z-popover)]",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </div>
  ) : null;
});

export const DropdownMenu = Object.assign(DropdownMenuRootStyled, {
  DropdownItem,
  DropdownDivider,
  HintBadge,
  // Also expose Radix primitives as sub-components for convenience
  Root: RadixDropdownMenu.Root,
  Trigger: RadixDropdownMenu.Trigger,
  Portal: RadixDropdownMenu.Portal,
  Content: DropdownMenuContent,
  Item: RadixDropdownMenu.Item,
  Separator: RadixDropdownMenu.Separator,
  Label: RadixDropdownMenu.Label,
  Group: RadixDropdownMenu.Group,
  Sub: RadixDropdownMenu.Sub,
  SubTrigger: RadixDropdownMenu.SubTrigger,
  SubContent: RadixDropdownMenu.SubContent,
  CheckboxItem: RadixDropdownMenu.CheckboxItem,
  RadioGroup: RadixDropdownMenu.RadioGroup,
  RadioItem: RadixDropdownMenu.RadioItem,
  ItemIndicator: RadixDropdownMenu.ItemIndicator,
  Arrow: RadixDropdownMenu.Arrow,
});
