"use client";
/**
 * Loader Component
 * 
 * A custom CSS spinner component.
 */

import React from "react";
import { cn } from "@/utils/cn";

interface LoaderRootProps extends React.HTMLAttributes<HTMLDivElement> {
  size?: "small" | "medium" | "large";
  className?: string;
}

const LoaderRoot = React.forwardRef<HTMLDivElement, LoaderRootProps>(
  function LoaderRoot(
    { size = "medium", className, ...otherProps }: LoaderRootProps,
    ref
  ) {
    return (
      <div
        className={cn(
          "inline-block animate-spin rounded-full border-2 border-solid border-current border-r-transparent",
          "text-body font-body text-brand-600",
          {
            "h-6 w-6 text-heading-2 font-heading-2": size === "large",
            "h-4 w-4": size === "medium",
            "h-3 w-3 text-caption font-caption": size === "small",
          },
          className
        )}
        ref={ref}
        role="status"
        aria-label="Loading"
        {...otherProps}
      >
        <span className="sr-only">Loading...</span>
      </div>
    );
  }
);

export const Loader = LoaderRoot;
