"use client";
/**
 * Skeleton Circle Component
 * 
 * A custom CSS skeleton circle component.
 */

import React from "react";
import { cn } from "@/utils/cn";

interface SkeletonCircleRootProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "default" | "small" | "x-small";
  className?: string;
}

const SkeletonCircleRoot = React.forwardRef<HTMLDivElement, SkeletonCircleRootProps>(
  function SkeletonCircleRoot(
    { size = "default", className, ...otherProps }: SkeletonCircleRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "group/8b6e7a84 flex h-9 w-9 flex-col items-start gap-2 rounded-full bg-neutral-200 animate-pulse",
          { "h-5 w-5": size === "x-small", "h-7 w-7": size === "small" },
          className
        )}
        ref={ref}
        {...otherProps}
      />
    );
  }
);

export const SkeletonCircle = SkeletonCircleRoot;
