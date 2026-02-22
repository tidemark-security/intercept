"use client";

import React from "react";

import { cn } from "@/utils/cn";

import { ChevronRight } from 'lucide-react';
interface ItemProps extends React.HTMLAttributes<HTMLSpanElement> {
  children?: React.ReactNode;
  active?: boolean;
  className?: string;
}

const Item = React.forwardRef<HTMLSpanElement, ItemProps>(function Item(
  { children, active = false, className, ...otherProps }: ItemProps,
  ref
) {
  return children ? (
    <span
      className={cn(
        "group/bbdc1640 line-clamp-1 cursor-pointer break-words text-body font-body text-subtext-color hover:text-default-font",
        { "text-default-font": active },
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </span>
  ) : null;
});

interface DividerProps
  extends React.ComponentProps<typeof ChevronRight> {
  className?: string;
}

const Divider = React.forwardRef<
  React.ElementRef<typeof ChevronRight>,
  DividerProps
>(function Divider({ className, ...otherProps }: DividerProps, ref) {
  return (
    <ChevronRight
      className={cn(
        "text-body font-body text-subtext-color",
        className
      )}
      ref={ref}
      {...otherProps}
    />
  );
});

interface BreadcrumbsRootProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

const BreadcrumbsRoot = React.forwardRef<HTMLDivElement, BreadcrumbsRootProps>(
  function BreadcrumbsRoot(
    { children, className, ...otherProps }: BreadcrumbsRootProps,
    ref
  ) {
    return children ? (
      <div
        className={cn(
          "flex items-center gap-2",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {children}
      </div>
    ) : null;
  }
);

export const Breadcrumbs = Object.assign(BreadcrumbsRoot, {
  Item,
  Divider,
});
