"use client";
/**
 * Select Component
 * 
 * A select/dropdown built on Radix UI primitives with proper z-index layering.
 * Uses PortalContainerContext to render the dropdown inside modals when appropriate.
 */

import React from "react";
import * as RadixSelect from "@radix-ui/react-select";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { usePortalContainer } from "@/contexts/PortalContainerContext";
import { useTheme } from "@/contexts/ThemeContext";
import { Check, ChevronDown } from 'lucide-react';

interface ItemProps extends React.ComponentPropsWithoutRef<typeof RadixSelect.Item> {
  value: string;
  children?: React.ReactNode;
  className?: string;
}

const Item = React.forwardRef<HTMLDivElement, ItemProps>(function Item(
  { value, children, className, ...otherProps }: ItemProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  return (
    <RadixSelect.Item
      value={value}
      className={cn(
        "group/969e345b flex h-8 w-full cursor-pointer items-center gap-1 rounded-md px-3 outline-none",
        "active:bg-neutral-50",
        isDarkTheme
          ? "hover:bg-neutral-100 focus:bg-neutral-100 data-[highlighted]:bg-neutral-100"
          : "hover:bg-brand-primary focus:bg-brand-primary data-[highlighted]:bg-brand-primary",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <RadixSelect.ItemText asChild>
        <span className="h-auto grow shrink-0 basis-0 text-body font-body text-default-font">
          {children || value}
        </span>
      </RadixSelect.ItemText>
      <RadixSelect.ItemIndicator>
        <Check className="text-body font-body text-neutral-1000" />
      </RadixSelect.ItemIndicator>
    </RadixSelect.Item>
  );
});

interface TriggerValueProps extends React.ComponentPropsWithoutRef<typeof RadixSelect.Value> {
  placeholder?: string;
  className?: string;
}

const TriggerValue = React.forwardRef<HTMLSpanElement, TriggerValueProps>(
  function TriggerValue(
    { placeholder, className, ...otherProps }: TriggerValueProps,
    ref
  ) {
    return (
      <RadixSelect.Value
        className={cn(
          "w-full whitespace-nowrap text-body font-body text-default-font data-[placeholder]:text-neutral-400",
          className
        )}
        ref={ref}
        placeholder={placeholder}
        {...otherProps}
      />
    );
  }
);

interface ContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

const Content = React.forwardRef<HTMLDivElement, ContentProps>(function Content(
  { children, className, ...otherProps }: ContentProps,
  ref
) {
  const portalContainer = usePortalContainer();
  
  return children ? (
    <RadixSelect.Portal container={portalContainer}>
      <RadixSelect.Content
        className={cn(
          "flex w-[var(--radix-select-trigger-width)] flex-col items-start overflow-hidden rounded-md border border-solid border-neutral-border bg-default-background px-1 py-1 shadow-lg",
          "z-[var(--z-popover)]",
          // Animations
          "data-[state=open]:animate-in data-[state=closed]:animate-out",
          "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
          "data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2",
          "data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
          className
        )}
        position="popper"
        sideOffset={4}
        ref={ref}
        {...otherProps}
      >
        <RadixSelect.Viewport className="w-full">
          {children}
        </RadixSelect.Viewport>
      </RadixSelect.Content>
    </RadixSelect.Portal>
  ) : null;
});

interface TriggerProps {
  placeholder?: string;
  icon?: React.ReactNode;
  className?: string;
}

const Trigger = React.forwardRef<HTMLButtonElement, TriggerProps>(function Trigger(
  { placeholder, icon = null, className, ...otherProps }: TriggerProps,
  ref
) {
  return (
    <RadixSelect.Trigger
      className={cn(
        "flex h-full w-full items-center gap-2 px-3 outline-none",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {icon ? (
        <IconWrapper className="text-body font-body text-neutral-400">
          {icon}
        </IconWrapper>
      ) : null}
      <span className="grow shrink-0 basis-0 text-left text-body font-body text-neutral-400">
        <Select.TriggerValue placeholder={placeholder} />
      </span>
      <RadixSelect.Icon className="flex-shrink-0">
        <ChevronDown className="text-body font-body text-subtext-color" />
      </RadixSelect.Icon>
    </RadixSelect.Trigger>
  );
});

interface ItemTextProps {
  children?: React.ReactNode;
  className?: string;
}

const ItemText = React.forwardRef<HTMLSpanElement, ItemTextProps>(
  function ItemText(
    { children, className, ...otherProps }: ItemTextProps,
    ref
  ) {
    return children ? (
      <span
        className={cn(
          "text-body font-body text-default-font",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {children}
      </span>
    ) : null;
  }
);

interface SelectRootProps {
  disabled?: boolean;
  error?: boolean;
  variant?: "outline" | "filled";
  label?: React.ReactNode;
  placeholder?: string;
  helpText?: React.ReactNode;
  icon?: React.ReactNode;
  children?: React.ReactNode;
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  dir?: "ltr" | "rtl";
  name?: string;
  autoComplete?: string;
  required?: boolean;
  form?: string;
  className?: string;
}

const SelectRoot = React.forwardRef<HTMLDivElement, SelectRootProps>(
  function SelectRoot(
    {
      disabled = false,
      error = false,
      variant = "outline",
      label,
      placeholder,
      helpText,
      icon = null,
      children,
      className,
      value,
      defaultValue,
      onValueChange,
      open,
      defaultOpen,
      onOpenChange,
      dir,
      name,
      required,
      ...otherProps
    }: SelectRootProps,
    ref
  ) {
    return (
      <RadixSelect.Root
        disabled={disabled}
        value={value}
        defaultValue={defaultValue}
        onValueChange={onValueChange}
        open={open}
        defaultOpen={defaultOpen}
        onOpenChange={onOpenChange}
        dir={dir}
        name={name}
        required={required}
      >
        <div
          className={cn(
            "group/bb88f90b flex cursor-pointer flex-col items-start gap-1",
            className
          )}
          ref={ref}
          {...otherProps}
        >
          {label ? (
            <span className="text-caption-bold font-caption-bold text-default-font">
              {label}
            </span>
          ) : null}
          <div
            className={cn(
              "flex h-8 w-full flex-none flex-col items-start rounded-md border border-solid border-neutral-border bg-default-background group-focus-within/bb88f90b:border group-focus-within/bb88f90b:border-solid group-focus-within/bb88f90b:border-focus-border",
              {
                "border border-solid border-neutral-100 bg-neutral-100 group-hover/bb88f90b:border group-hover/bb88f90b:border-solid group-hover/bb88f90b:border-neutral-border group-hover/bb88f90b:bg-neutral-100":
                  variant === "filled",
                "border border-solid border-error-600": error,
                "bg-neutral-200": disabled,
              }
            )}
          >
            <Trigger placeholder={placeholder} icon={icon} />
          </div>
          {helpText ? (
            <span
              className={cn(
                "text-caption font-caption text-subtext-color",
                { "text-error-700": error }
              )}
            >
              {helpText}
            </span>
          ) : null}
          <Content>
            {children ? (
              <div className="flex w-full grow shrink-0 basis-0 flex-col items-start">
                {children}
              </div>
            ) : null}
          </Content>
        </div>
      </RadixSelect.Root>
    );
  }
);

export const Select = Object.assign(SelectRoot, {
  Item,
  TriggerValue,
  Content,
  Trigger,
  ItemText,
});
