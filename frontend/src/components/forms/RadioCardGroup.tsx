"use client";

import React from "react";
import * as RadixRadioGroup from "@radix-ui/react-radio-group";
import { cn } from "@/utils/cn";
import { useTheme } from "@/contexts/ThemeContext";

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
    const { resolvedTheme } = useTheme();
    const isDarkTheme = resolvedTheme === "dark";

    return (
      <RadixRadioGroup.Item
        disabled={disabled}
        asChild={true}
        {...otherProps}
      >
        <button
          className={cn(
            "group/502d4919 flex w-full cursor-pointer items-center gap-4 rounded-sm border border-solid border-neutral-border bg-neutral-0 px-4 py-3 text-left",
            {
              "text-[#fafafaff] hover:border hover:border-solid hover:border-brand-primary hover:text-brand-400":
                isDarkTheme,
              "text-default-font hover:bg-brand-primary hover:border-brand-700":
                !isDarkTheme,
              "data-[state=checked]:border data-[state=checked]:border-solid data-[state=checked]:border-accent-1-primary data-[state=checked]:text-accent-1-400":
                isDarkTheme,
              "data-[state=checked]:bg-neutral-300 data-[state=checked]:border-neutral-900":
                !isDarkTheme,
              "disabled:cursor-default disabled:border disabled:border-solid disabled:border-neutral-100 disabled:bg-neutral-50 disabled:text-subtext-color hover:disabled:cursor-default hover:disabled:bg-neutral-50":
                true,
            },
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
            <div
              className={cn(
                "flex h-4 w-4 flex-none flex-col items-center justify-center gap-2 rounded-full border-2 border-solid border-neutral-300 group-data-[state=checked]/502d4919:border-2 group-data-[state=checked]/502d4919:border-solid group-disabled/502d4919:border-2 group-disabled/502d4919:border-solid group-disabled/502d4919:border-neutral-300 group-disabled/502d4919:bg-neutral-100",
                {
                  "group-data-[state=checked]/502d4919:border-accent-1-primary":
                    isDarkTheme,
                  "group-data-[state=checked]/502d4919:border-neutral-900":
                    !isDarkTheme,
                }
              )}
            >
              <div
                className={cn(
                  "hidden h-2 w-2 flex-none flex-col items-start gap-2 rounded-full bg-black group-data-[state=checked]/502d4919:flex group-disabled/502d4919:bg-neutral-300",
                  {
                    "group-data-[state=checked]/502d4919:bg-accent-1-primary":
                      isDarkTheme,
                    "group-data-[state=checked]/502d4919:bg-neutral-900":
                      !isDarkTheme,
                  }
                )}
              />
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
