import React from "react";
import * as RadixToggleGroup from "@radix-ui/react-toggle-group";
import { Star } from "lucide-react";

import { useTheme } from "@/contexts/ThemeContext";
import { IconWrapper } from "@/utils/IconWrapper";
import { cn } from "@/utils/cn";

type ToggleGroupVariant = "default" | "button" | "two-line-button";
type ToggleGroupLabelDisplay = "inline" | "tooltip";

interface ToggleGroupContextValue {
  variant: ToggleGroupVariant;
  labelDisplay: ToggleGroupLabelDisplay;
}

const ToggleGroupContext = React.createContext<ToggleGroupContextValue>({
  variant: "default",
  labelDisplay: "inline",
});

function getTextFromNode(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }

  if (Array.isArray(node)) {
    return node.map(getTextFromNode).filter(Boolean).join(" ");
  }

  if (React.isValidElement<{ children?: React.ReactNode }>(node)) {
    return getTextFromNode(node.props.children);
  }

  return "";
}

interface ItemProps
  extends Omit<React.ComponentPropsWithoutRef<typeof RadixToggleGroup.Item>, "value"> {
  disabled?: boolean;
  children?: React.ReactNode;
  icon?: React.ReactNode;
  value?: string;
  className?: string;
}

const Item = React.forwardRef<HTMLButtonElement, ItemProps>(function Item(
  { disabled = false, children, icon = <Star />, value, className, title, ...otherProps },
  ref,
) {
  const { resolvedTheme } = useTheme();
  const { variant, labelDisplay } = React.useContext(ToggleGroupContext);
  const selectedTextClass =
    resolvedTheme === "dark"
      ? "group-data-[state=on]/56dea6ed:text-brand-primary"
      : "group-data-[state=on]/56dea6ed:text-brand-700";
  const hoverBackgroundClass =
    resolvedTheme === "dark"
      ? "hover:bg-neutral-100 active:bg-neutral-100"
      : "hover:bg-neutral-300 active:bg-neutral-300";
  const isButtonVariant = variant === "button";
  const isTwoLineButtonVariant = variant === "two-line-button";
  const isLargeButtonVariant = isButtonVariant || isTwoLineButtonVariant;
  const tooltipTitle = title ?? (labelDisplay === "tooltip" ? getTextFromNode(children) : undefined);
  const hideChildrenForTooltip = labelDisplay === "tooltip" && !title;

  return (
    <RadixToggleGroup.Item
      value={value || ""}
      disabled={disabled}
      className={cn(
        "group/56dea6ed flex w-auto cursor-pointer items-center justify-center gap-2 rounded-md border border-transparent",
        hoverBackgroundClass,
        "data-[state=on]:bg-default-background data-[state=on]:shadow-none",
        isButtonVariant
          ? "min-h-14 min-w-24 flex-col gap-1 px-4 py-2 text-center data-[state=on]:bg-brand-primary"
          : isTwoLineButtonVariant
            ? "min-h-14 min-w-32 flex-row justify-start gap-3 px-3 py-2 text-left data-[state=on]:bg-brand-primary"
          : "h-7 px-2 py-1",
        {
          "cursor-not-allowed opacity-50 hover:bg-transparent active:bg-transparent": disabled,
        },
        className,
      )}
      ref={ref}
      title={tooltipTitle}
      {...otherProps}
    >
      {icon ? (
        <IconWrapper
          className={cn(
            "text-body font-body text-subtext-color",
            "group-hover/56dea6ed:text-default-font group-active/56dea6ed:text-default-font",
            "group-data-[state=on]/56dea6ed:scale-105",
            isLargeButtonVariant
              ? "text-heading-3 font-heading-3 group-data-[state=on]/56dea6ed:text-black"
              : selectedTextClass,
            isTwoLineButtonVariant && "flex-none",
            {
              "text-neutral-400 group-hover/56dea6ed:text-neutral-400 group-active/56dea6ed:text-neutral-400":
                disabled,
            },
          )}
        >
          {icon}
        </IconWrapper>
      ) : null}
      {children ? (
        <span
          className={cn(
            "whitespace-nowrap text-caption-bold font-caption-bold text-subtext-color",
            "group-hover/56dea6ed:text-default-font group-active/56dea6ed:text-default-font",
            hideChildrenForTooltip && "sr-only",
            isButtonVariant
              ? "text-center group-data-[state=on]/56dea6ed:text-black"
              : isTwoLineButtonVariant
                ? "min-w-0 text-left group-data-[state=on]/56dea6ed:text-black"
              : "group-data-[state=on]/56dea6ed:underline group-data-[state=on]/56dea6ed:underline-offset-2",
            !isLargeButtonVariant && selectedTextClass,
            {
              "text-neutral-400 group-hover/56dea6ed:text-neutral-400 group-active/56dea6ed:text-neutral-400":
                disabled,
            },
          )}
        >
          {children}
        </span>
      ) : null}
    </RadixToggleGroup.Item>
  );
});

type ToggleGroupSingleProps = {
  type?: "single";
  value?: string;
  onValueChange?: (value: string) => void;
  children?: React.ReactNode;
  className?: string;
  variant?: ToggleGroupVariant;
  labelDisplay?: ToggleGroupLabelDisplay;
};

type ToggleGroupMultipleProps = {
  type: "multiple";
  value?: string[];
  onValueChange?: (value: string[]) => void;
  children?: React.ReactNode;
  className?: string;
  variant?: ToggleGroupVariant;
  labelDisplay?: ToggleGroupLabelDisplay;
};

type ToggleGroupRootProps = ToggleGroupSingleProps | ToggleGroupMultipleProps;

const ToggleGroupRoot = React.forwardRef<HTMLDivElement, ToggleGroupRootProps>(
  function ToggleGroupRoot(props, ref) {
    const { children, className, variant = "default", labelDisplay = "inline" } = props;
    const rootClassName = cn(
      "flex flex-wrap items-center justify-center gap-0.5 overflow-hidden rounded-md bg-default-background px-0.5 py-0.5",
      (variant === "button" || variant === "two-line-button") && "items-stretch",
      className,
    );

    if (!children) {
      return null;
    }

    if (props.type === "multiple") {
      const { value = [], onValueChange } = props;

      return (
        <ToggleGroupContext.Provider value={{ variant, labelDisplay }}>
          <RadixToggleGroup.Root
            type="multiple"
            value={value}
            onValueChange={onValueChange}
            className={rootClassName}
            ref={ref}
          >
            {children}
          </RadixToggleGroup.Root>
        </ToggleGroupContext.Provider>
      );
    }

    const { value, onValueChange } = props;

    return (
      <ToggleGroupContext.Provider value={{ variant, labelDisplay }}>
        <RadixToggleGroup.Root
          type="single"
          value={value}
          onValueChange={onValueChange}
          className={rootClassName}
          ref={ref}
        >
          {children}
        </RadixToggleGroup.Root>
      </ToggleGroupContext.Provider>
    );
  },
);

export const ToggleGroup = Object.assign(ToggleGroupRoot, {
  Item,
});
