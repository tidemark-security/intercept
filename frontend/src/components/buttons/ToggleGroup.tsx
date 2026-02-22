
"use client";
/**
 * Toggle Group Component
 * 
 * A toggle group built on Radix UI primitives.
 */

import React from "react";
import * as RadixToggleGroup from "@radix-ui/react-toggle-group";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/utils/cn";
import { IconWrapper } from "@/utils/IconWrapper";
import { Star } from 'lucide-react';

interface ItemProps extends Omit<React.ComponentPropsWithoutRef<typeof RadixToggleGroup.Item>, 'value'> {
  disabled?: boolean;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  value?: string;
  className?: string;
}

const Item = React.forwardRef<HTMLButtonElement, ItemProps>(function Item(
  {
    disabled = false,
    children,
    icon = <Star />,
    value,
    className,
    ...otherProps
  }: ItemProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const selectedTextClass = resolvedTheme === "dark" ? "group-data-[state=on]/56dea6ed:text-brand-primary" : "group-data-[state=on]/56dea6ed:text-brand-700";
  const hoverBackgroundClass = resolvedTheme === "dark" ? "hover:bg-neutral-100 active:bg-neutral-100" : "hover:bg-neutral-300 active:bg-neutral-300";

  return (
    <RadixToggleGroup.Item
      value={value || ''}
      disabled={disabled}
      className={cn(
        "group/56dea6ed flex h-7 w-auto cursor-pointer items-center justify-center gap-2 rounded-md border border-transparent px-2 py-1",
        hoverBackgroundClass,
        "data-[state=on]:bg-default-background data-[state=on]:shadow-none",
        
        { "hover:bg-transparent active:bg-transparent cursor-not-allowed opacity-50": disabled },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {icon ? (
        <IconWrapper
          className={cn(
            "text-body font-body text-subtext-color",
            "group-hover/56dea6ed:text-default-font group-active/56dea6ed:text-default-font",
            "group-data-[state=on]/56dea6ed:scale-105",
            selectedTextClass,
            {
              "text-neutral-400 group-hover/56dea6ed:text-neutral-400 group-active/56dea6ed:text-neutral-400":
                disabled,
            }
          )}
        >
          {icon}
        </IconWrapper>
      ) : null}
      {children ? (
        <span
          className={cn(
            "whitespace-nowrap text-caption-bold font-caption-bold text-subtext-color",
            "group-hover/56dea6ed:text-default-font group-active/56dea6ed:text-default-font",
            "group-data-[state=on]/56dea6ed:underline group-data-[state=on]/56dea6ed:underline-offset-2",
            selectedTextClass,
            {
              "text-neutral-400 group-hover/56dea6ed:text-neutral-400 group-active/56dea6ed:text-neutral-400":
                disabled,
            }
          )}
        >
          {children}
        </span>
      ) : null}
    </RadixToggleGroup.Item>
  );
});

type ToggleGroupSingleProps = {
  type?: "single";
  value?: string;
  onValueChange?: (value: string) => void;
  children?: React.ReactNode;
  className?: string;
};

type ToggleGroupMultipleProps = {
  type: "multiple";
  value?: string[];
  onValueChange?: (value: string[]) => void;
  children?: React.ReactNode;
  className?: string;
};

type ToggleGroupRootProps = ToggleGroupSingleProps | ToggleGroupMultipleProps;

const ToggleGroupRoot = React.forwardRef<HTMLDivElement, ToggleGroupRootProps>(
  function ToggleGroupRoot(
    props: ToggleGroupRootProps,
    ref
  ) {
    const { children, className } = props;
    
    if (props.type === "multiple") {
      const { value = [], onValueChange } = props;
      
      return children ? (
        <RadixToggleGroup.Root
          type="multiple"
          value={value}
          onValueChange={onValueChange}
          className={cn(
            "flex flex-wrap items-center justify-center gap-0.5 overflow-hidden rounded-md bg-default-background px-0.5 py-0.5",
            className
          )}
          ref={ref}
        >
          {children}
        </RadixToggleGroup.Root>
      ) : null;
    }
    
    // Handle single selection mode
    const { value, onValueChange } = props;
    return children ? (
      <RadixToggleGroup.Root
        type="single"
        value={value}
        onValueChange={onValueChange}
        className={cn(
          "flex flex-wrap items-center justify-center gap-0.5 overflow-hidden rounded-md bg-default-background px-0.5 py-0.5",
          className
        )}
        ref={ref}
      >
        {children}
      </RadixToggleGroup.Root>
    ) : null;
  }
);

export const ToggleGroup = Object.assign(ToggleGroupRoot, {
  Item,
});
