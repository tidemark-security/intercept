"use client";

import React from "react";
import * as RadixRadioGroup from "@radix-ui/react-radio-group";
import { cn } from "@/utils/cn";

interface RadioCardProps
  extends React.ComponentPropsWithoutRef<typeof RadixRadioGroup.Item> {
  disabled?: boolean;
  hideRadio?: boolean;
  children?: React.ReactNode;
  className?: string;
}

const RadioCard = React.forwardRef<HTMLButtonElement, RadioCardProps>(
  function RadioCard(
    {
      disabled = false,
      hideRadio = false,
      children,
      className,
      ...otherProps
    }: RadioCardProps,
    ref
  ) {
    return (
      <RadixRadioGroup.Item
        disabled={disabled}
        asChild={true}
        {...otherProps}
      >
        <button
          className={cn(
            "group/502d4919 flex w-full cursor-pointer items-center gap-4 rounded-md border border-solid border-neutral-200 bg-default-background px-4 py-3 text-left hover:bg-neutral-50 data-[state=checked]:border data-[state=checked]:border-solid data-[state=checked]:border-brand-200 data-[state=checked]:bg-brand-800 hover:data-[state=checked]:border hover:data-[state=checked]:border-solid hover:data-[state=checked]:border-brand-200 hover:data-[state=checked]:bg-brand-900 disabled:cursor-default disabled:border disabled:border-solid disabled:border-neutral-100 disabled:bg-neutral-50 hover:disabled:cursor-default hover:disabled:bg-neutral-50",
            className
          )}
          ref={ref}
        >
          <div
            className={cn(
              "flex items-start gap-2 rounded-full pt-0.5",
              { hidden: hideRadio }
            )}
          >
            <div className="flex h-4 w-4 flex-none flex-col items-center justify-center gap-2 rounded-full border-2 border-solid border-neutral-300 group-data-[state=checked]/502d4919:border-2 group-data-[state=checked]/502d4919:border-solid group-data-[state=checked]/502d4919:border-brand-600 group-disabled/502d4919:border-2 group-disabled/502d4919:border-solid group-disabled/502d4919:border-neutral-300 group-disabled/502d4919:bg-neutral-100">
              <div className="hidden h-2 w-2 flex-none flex-col items-start gap-2 rounded-full bg-black group-data-[state=checked]/502d4919:flex group-data-[state=checked]/502d4919:bg-brand-600 group-disabled/502d4919:bg-neutral-300" />
            </div>
          </div>
          {children ? (
            <div className="flex grow shrink-0 basis-0 flex-col items-start gap-2">
              {children}
            </div>
          ) : null}
        </button>
      </RadixRadioGroup.Item>
    );
  }
);

interface RadioCardGroupRootProps
  extends React.ComponentPropsWithoutRef<typeof RadixRadioGroup.Root> {
  children?: React.ReactNode;
  value?: string;
  onValueChange?: (value: string) => void;
  className?: string;
}

const RadioCardGroupRoot = React.forwardRef<
  HTMLDivElement,
  RadioCardGroupRootProps
>(function RadioCardGroupRoot(
  { children, className, ...otherProps }: RadioCardGroupRootProps,
  ref
) {
  return children ? (
    <RadixRadioGroup.Root asChild={true} {...otherProps}>
      <div
        className={cn(
          "flex items-start gap-2",
          className
        )}
        ref={ref}
      >
        {children}
      </div>
    </RadixRadioGroup.Root>
  ) : null;
});

export const RadioCardGroup = Object.assign(RadioCardGroupRoot, {
  RadioCard,
});
