import React from "react";
import { ToggleGroup as UxToggleGroup } from "@tidemark-security/ux";

export type ToggleGroupLabelDisplay = "all" | "selected" | "none" | "tooltip";
export type ToggleGroupVariant = "default" | "compact" | "compact-button";

type UxToggleGroupType = typeof UxToggleGroup;
type UxToggleGroupItemType = typeof UxToggleGroup.Item;

type RootProps = React.ComponentPropsWithoutRef<UxToggleGroupType> & {
  labelDisplay?: ToggleGroupLabelDisplay;
  variant?: ToggleGroupVariant;
};

type ItemProps = React.ComponentPropsWithoutRef<UxToggleGroupItemType> & {
  tooltip?: React.ReactNode;
};

const Root = React.forwardRef<HTMLDivElement, RootProps>(function ToggleGroupRoot(
  { labelDisplay: _labelDisplay, variant: _variant, ...props },
  ref,
) {
  const Component = UxToggleGroup as React.ForwardRefExoticComponent<
    React.PropsWithoutRef<React.ComponentPropsWithoutRef<UxToggleGroupType>> &
      React.RefAttributes<HTMLDivElement>
  >;
  return <Component ref={ref} {...props} />;
});

const Item = React.forwardRef<HTMLButtonElement, ItemProps>(function ToggleGroupItem(
  { tooltip: _tooltip, ...props },
  ref,
) {
  const Component = UxToggleGroup.Item as React.ForwardRefExoticComponent<
    React.PropsWithoutRef<React.ComponentPropsWithoutRef<UxToggleGroupItemType>> &
      React.RefAttributes<HTMLButtonElement>
  >;
  return <Component ref={ref} {...props} />;
});

export const ToggleGroup = Object.assign(Root, {
  Item,
});
