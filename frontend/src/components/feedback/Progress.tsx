"use client";
/**
 * Progress Component
 * 
 * A progress bar built on Radix UI primitives.
 */

import React from "react";
import * as RadixProgress from "@radix-ui/react-progress";
import { cn } from "@/utils/cn";

interface IndicatorProps extends React.ComponentPropsWithoutRef<typeof RadixProgress.Indicator> {
  className?: string;
}

const Indicator = React.forwardRef<HTMLDivElement, IndicatorProps>(
  function Indicator({ className, style, ...otherProps }: IndicatorProps, ref) {
    return (
      <RadixProgress.Indicator
        className={cn(
          "h-2 w-full bg-brand-600 transition-transform",
          className
        )}
        style={style}
        ref={ref}
        {...otherProps}
      />
    );
  }
);

interface ProgressRootProps extends React.ComponentPropsWithoutRef<typeof RadixProgress.Root> {
  value?: number;
  className?: string;
}

const ProgressRoot = React.forwardRef<HTMLDivElement, ProgressRootProps>(
  function ProgressRoot(
    { value = 30, className, ...otherProps }: ProgressRootProps,
    ref
  ) {
    return (
      <RadixProgress.Root
        className={cn(
          "relative w-full overflow-hidden bg-brand-1000 h-2",
          className
        )}
        value={value}
        ref={ref}
        {...otherProps}
      >
        <Indicator
          style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
        />
      </RadixProgress.Root>
    );
  }
);

export const Progress = Object.assign(ProgressRoot, {
  Indicator,
});
