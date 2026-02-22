"use client";

import React from "react";

import { cn } from "@/utils/cn";

import { Check } from 'lucide-react';
interface StepProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "completed" | "active";
  stepNumber?: React.ReactNode;
  label?: React.ReactNode;
  firstStep?: boolean;
  lastStep?: boolean;
  children?: React.ReactNode;
  className?: string;
}

const Step = React.forwardRef<HTMLDivElement, StepProps>(function Step(
  {
    variant = "default",
    stepNumber,
    label,
    firstStep = false,
    lastStep = false,
    children,
    className,
    ...otherProps
  }: StepProps,
  ref
) {
  return (
    <div
      className={cn(
        "group/b094efab flex h-full w-full items-start gap-3",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      <div
        className={cn(
          "flex flex-col items-center gap-1 self-stretch",
          { "h-auto w-auto flex-none": lastStep }
        )}
      >
        <div
          className={cn(
            "flex h-2 w-0.5 flex-none flex-col items-center gap-2 bg-neutral-border",
            { "h-2 w-0.5 flex-none": lastStep, hidden: firstStep }
          )}
        />
        <div
          className={cn(
            "flex h-7 w-7 flex-none items-center justify-center overflow-hidden rounded-full bg-neutral-100",
            { "bg-brand-100": variant === "active" || variant === "completed" }
          )}
        >
          {stepNumber ? (
            <span
              className={cn(
                "text-body-bold font-body-bold text-subtext-color text-center",
                {
                  "text-body-bold font-body-bold text-brand-700":
                    variant === "active",
                  hidden: variant === "completed",
                }
              )}
            >
              {stepNumber}
            </span>
          ) : null}
          <Check
            className={cn(
              "hidden text-heading-3 font-heading-3 text-default-font",
              { "inline-flex text-brand-700": variant === "completed" }
            )}
          />
        </div>
        <div
          className={cn(
            "flex min-h-[8px] w-0.5 grow shrink-0 basis-0 flex-col items-center gap-2 bg-neutral-border",
            { hidden: lastStep }
          )}
        />
      </div>
      <div
        className={cn(
          "flex grow shrink-0 basis-0 flex-col items-center gap-1 py-4",
          { "px-0 pt-4 pb-1": lastStep, "px-0 pt-1 pb-4": firstStep }
        )}
      >
        {label ? (
          <span
            className={cn(
              "line-clamp-2 w-full text-body font-body text-subtext-color",
              {
                "text-body-bold font-body-bold text-default-font":
                  variant === "active",
                "text-body font-body text-default-font":
                  variant === "completed",
              }
            )}
          >
            {label}
          </span>
        ) : null}
        {children ? (
          <div className="flex w-full flex-col items-start gap-2">
            {children}
          </div>
        ) : null}
      </div>
    </div>
  );
});

interface VerticalStepperRootProps
  extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

const VerticalStepperRoot = React.forwardRef<
  HTMLDivElement,
  VerticalStepperRootProps
>(function VerticalStepperRoot(
  { children, className, ...otherProps }: VerticalStepperRootProps,
  ref
) {
  return children ? (
    <div
      className={cn(
        "flex flex-col items-start",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </div>
  ) : null;
});

export const VerticalStepper = Object.assign(VerticalStepperRoot, {
  Step,
});
