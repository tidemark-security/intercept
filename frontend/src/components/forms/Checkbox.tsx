import React from "react";
import * as RadixCheckbox from "@radix-ui/react-checkbox";
import { Check, Minus } from "lucide-react";

import { cn } from "@/utils/cn";

export interface CheckboxProps
  extends Omit<React.ComponentPropsWithoutRef<typeof RadixCheckbox.Root>, "checked" | "onCheckedChange"> {
  checked?: boolean;
  indeterminate?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  size?: "small" | "medium";
}

export const Checkbox = React.forwardRef<HTMLButtonElement, CheckboxProps>(function Checkbox(
  {
    checked = false,
    indeterminate = false,
    onCheckedChange,
    size = "medium",
    className,
    ...props
  },
  ref,
) {
  const iconClassName = size === "small" ? "h-3 w-3" : "h-3.5 w-3.5";

  return (
    <RadixCheckbox.Root
      ref={ref}
      checked={indeterminate ? "indeterminate" : checked}
      onCheckedChange={(value) => onCheckedChange?.(value === true)}
      className={cn(
        "flex shrink-0 items-center justify-center border border-solid border-neutral-border bg-default-background text-brand-primary",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-primary",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "small" ? "h-4 w-4" : "h-5 w-5",
        className,
      )}
      {...props}
    >
      <RadixCheckbox.Indicator className="flex items-center justify-center">
        {indeterminate ? <Minus className={iconClassName} /> : <Check className={iconClassName} />}
      </RadixCheckbox.Indicator>
    </RadixCheckbox.Root>
  );
});
