"use client";

import React from "react";

import { cn } from "@/utils/cn";

export interface ToolbarProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  minItemWidth?: string;
  className?: string;
}

export const Toolbar = React.forwardRef<HTMLDivElement, ToolbarProps>(
  function Toolbar(
    { children, minItemWidth = "112px", className, style, ...otherProps },
    ref,
  ) {
    return (
      <div
        className={cn(
          "flex w-full flex-col overflow-hidden rounded-md bg-[color-mix(in_srgb,rgb(var(--color-neutral-100))_88%,black)]",
          className,
        )}
        ref={ref}
        style={{
          "--toolbar-min-item-width": minItemWidth,
          ...style,
        } as React.CSSProperties}
        {...otherProps}
      >
        <div className="grid w-full grid-cols-[repeat(auto-fit,minmax(var(--toolbar-min-item-width),1fr))] gap-px">
          {children}
        </div>
      </div>
    );
  },
);
