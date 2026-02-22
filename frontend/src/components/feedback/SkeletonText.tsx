"use client";
/**
 * Skeleton Text Component
 * 
 * A custom CSS skeleton text component.
 */

import React from "react";
import { cn } from "@/utils/cn";

interface SkeletonTextRootProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "default" | "label" | "subheader" | "section-header" | "header";
  className?: string;
}

const SkeletonTextRoot = React.forwardRef<HTMLDivElement, SkeletonTextRootProps>(
  function SkeletonTextRoot(
    { size = "default", className, ...otherProps }: SkeletonTextRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "group/a9aae3f0 flex h-5 w-full flex-col items-start gap-2 rounded-md bg-neutral-200 animate-pulse",
          {
            "h-10 w-full": size === "header",
            "h-9 w-full": size === "section-header",
            "h-7 w-full": size === "subheader",
            "h-4 w-full": size === "label",
          },
          className
        )}
        ref={ref}
        {...otherProps}
      />
    );
  }
);

export const SkeletonText = SkeletonTextRoot;
