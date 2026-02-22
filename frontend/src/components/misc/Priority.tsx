
"use client";

import React from "react";






import { cn } from "@/utils/cn";

import { BellRing, ChevronDown, ChevronUp, ChevronsDown, ChevronsUp, Info } from 'lucide-react';
interface PriorityRootProps extends React.HTMLAttributes<HTMLDivElement> {
  priority?: "info" | "low" | "medium" | "high" | "critical" | "extreme";
  size?: "small" | "mini" | "maxi";
  className?: string;
}

const PriorityRoot = React.forwardRef<HTMLDivElement, PriorityRootProps>(
  function PriorityRoot(
    {
      priority = "info",
      size = "small",
      className,
      ...otherProps
    }: PriorityRootProps,
    ref
  ) {
    const isExtreme = priority === "extreme";
    const isCritical = priority === "critical";
    const isHigh = priority === "high";
    const isMedium = priority === "medium";
    const isLow = priority === "low";
    const highlightPriority = isExtreme || isCritical || isHigh || isMedium;

    const isInfo = !isExtreme && !isCritical && !isHigh && !isMedium && !isLow;

    return (
      <div
        className={cn(
          "group/58f5a1fe flex h-6 w-20 items-center gap-1 rounded-md border border-solid border-neutral-border px-2",
          {
            "h-9 w-32": size === "maxi",
            "h-6 w-auto": size === "mini",
            "bg-p0": isExtreme,
            "bg-p1": isCritical,
            "bg-p2": isHigh,
            "bg-p3": isMedium,
            "bg-p4": isLow,
            "bg-p5": isInfo,
          },
          className
        )}
        ref={ref}
        {...otherProps}
      >
        {isExtreme ? (
          <BellRing
            className={cn(
              "text-body font-body text-black",
              {
                "text-heading-2 font-heading-2": size === "maxi",
                "text-white": highlightPriority,
              }
            )}
          />
        ) : isCritical ? (
          <ChevronsUp
            className={cn(
              "text-body font-body text-black",
              {
                "text-heading-2 font-heading-2": size === "maxi",
                "text-white": highlightPriority,
              }
            )}
          />
        ) : isHigh ? (
          <ChevronUp
            className={cn(
              "text-body font-body text-black",
              {
                "text-heading-2 font-heading-2": size === "maxi",
                "text-white": highlightPriority,
              }
            )}
          />
        ) : isMedium ? (
          <ChevronDown
            className={cn(
              "text-body font-body text-black",
              {
                "text-heading-2 font-heading-2": size === "maxi",
                "text-white": highlightPriority,
              }
            )}
          />
        ) : isLow ? (
          <ChevronsDown
            className={cn(
              "text-body font-body text-black",
              {
                "text-heading-2 font-heading-2": size === "maxi",
                "text-white": highlightPriority,
              }
            )}
          />
        ) : (
          <Info
            className={cn(
              "text-body font-body text-black",
              {
                "text-heading-2 font-heading-2": size === "maxi",
                "text-white": highlightPriority,
              }
            )}
          />
        )}
        <span
          className={cn(
            "grow shrink-0 basis-0 whitespace-nowrap text-caption font-caption text-black text-center",
            {
              "text-heading-2 font-heading-2": size === "maxi",
              hidden: size === "mini",
              "text-white": highlightPriority,
            }
          )}
        >
          {isExtreme
            ? "Extreme"
            : isCritical
            ? "Critical"
            : isHigh
            ? "High"
            : isMedium
            ? "Medium"
            : isLow
            ? "Low"
            : "Info"}
        </span>
      </div>
    );
  }
);

export const Priority = PriorityRoot;
