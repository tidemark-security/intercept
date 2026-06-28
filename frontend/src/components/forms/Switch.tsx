import React from "react";
import { Switch as UxSwitch } from "@tidemark-security/ux";

export type SwitchProps = React.ComponentPropsWithoutRef<typeof UxSwitch> & {
  label?: boolean;
};

export const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(function Switch(
  { label: _label, ...props },
  ref,
) {
  const Component = UxSwitch as React.ForwardRefExoticComponent<
    React.PropsWithoutRef<React.ComponentPropsWithoutRef<typeof UxSwitch>> &
      React.RefAttributes<HTMLButtonElement>
  >;
  return <Component ref={ref} {...props} />;
});
