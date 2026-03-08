"use client";
/**
 * Slider Component
 * 
 * A slider built on Radix UI primitives.
 */

import React from "react";
import * as RadixSlider from "@radix-ui/react-slider";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";

interface RangeProps extends React.ComponentPropsWithoutRef<typeof RadixSlider.Range> {
  className?: string;
}

const Range = React.forwardRef<HTMLSpanElement, RangeProps>(function Range(
  { className, ...otherProps }: RangeProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  return (
    <RadixSlider.Range
      className={cn(
        "absolute h-full rounded-sm",
        isDarkTheme ? "bg-brand-primary" : "bg-neutral-1000",
        className
      )}
      ref={ref}
      {...otherProps}
    />
  );
});

interface ThumbProps extends React.ComponentPropsWithoutRef<typeof RadixSlider.Thumb> {
  className?: string;
}

const Thumb = React.forwardRef<HTMLSpanElement, ThumbProps>(function Thumb(
  { className, ...otherProps }: ThumbProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  return (
    <RadixSlider.Thumb
      className={cn(
        "block h-5 w-2.5 rounded-custom5",
        isDarkTheme ? "bg-brand-primary" : "bg-neutral-1000",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2",
        isDarkTheme ? "focus-visible:ring-brand-500" : "focus-visible:ring-neutral-1000",
        "disabled:pointer-events-none disabled:opacity-50",
        className
      )}
      ref={ref}
      {...otherProps}
    />
  );
});

interface TrackProps extends React.ComponentPropsWithoutRef<typeof RadixSlider.Track> {
  className?: string;
}

const Track = React.forwardRef<HTMLSpanElement, TrackProps>(function Track(
  { className, ...otherProps }: TrackProps,
  ref
) {
  const { resolvedTheme } = useTheme();
  const isDarkTheme = resolvedTheme === "dark";

  return (
    <RadixSlider.Track
      className={cn(
        "relative h-1.5 w-full grow rounded-sm",
        isDarkTheme ? "bg-neutral-100" : "bg-neutral-200",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <Range />
    </RadixSlider.Track>
  );
});

interface SliderRootProps extends React.ComponentPropsWithoutRef<typeof RadixSlider.Root> {
  value?: number[];
  onValueChange?: (value: number[]) => void;
  onValueCommit?: (value: number[]) => void;
  className?: string;
}

const SliderRoot = React.forwardRef<HTMLSpanElement, SliderRootProps>(
  function SliderRoot({ className, ...otherProps }: SliderRootProps, ref) {
    return (
      <RadixSlider.Root
        className={cn(
          "relative flex h-5 w-full cursor-pointer touch-none select-none items-center",
          className
        )}
        ref={ref}
        {...otherProps}
      >
        <Track />
        <Thumb />
      </RadixSlider.Root>
    );
  }
);

export const Slider = Object.assign(SliderRoot, {
  Range,
  Thumb,
  Track,
});
