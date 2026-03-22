"use client";
/**
 * Accordion Component
 * 
 * A collapsible accordion built on Radix UI primitives.
 */

import React from "react";
import * as RadixCollapsible from "@radix-ui/react-collapsible";
import { cn } from "@/utils/cn";
import { ChevronDown } from 'lucide-react';

interface ChevronProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

const Chevron = React.forwardRef<HTMLDivElement, ChevronProps>(
  function Chevron({ className, ...otherProps }: ChevronProps, ref) {
    return (
      <div
        className={cn(
          "transition-transform duration-200",
          "group-data-[state=open]/d2e81e20:rotate-180"
        )}
        ref={ref}
        {...otherProps}
      >
        <ChevronDown
          className={cn(
            "text-body font-body text-default-font",
            className
          )}
        />
      </div>
    );
  }
);

interface ContentProps extends React.ComponentPropsWithoutRef<typeof RadixCollapsible.Content> {
  children?: React.ReactNode;
  className?: string;
}

const Content = React.forwardRef<HTMLDivElement, ContentProps>(function Content(
  { children, className, ...otherProps }: ContentProps,
  ref
) {
  return children ? (
    <RadixCollapsible.Content
      className={cn(
        "flex w-full flex-col items-start gap-2 overflow-hidden",
        "data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </RadixCollapsible.Content>
  ) : null;
});

interface TriggerProps extends React.ComponentPropsWithoutRef<typeof RadixCollapsible.Trigger> {
  children?: React.ReactNode;
  className?: string;
}

const Trigger = React.forwardRef<HTMLButtonElement, TriggerProps>(function Trigger(
  { children, className, ...otherProps }: TriggerProps,
  ref
) {
  return children ? (
    <RadixCollapsible.Trigger
      className={cn(
        "flex w-full cursor-pointer flex-col items-start gap-2",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </RadixCollapsible.Trigger>
  ) : null;
});

interface AccordionRootProps {
  trigger?: React.ReactNode;
  children?: React.ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

const AccordionRoot = React.forwardRef<HTMLDivElement, AccordionRootProps>(
  function AccordionRoot(
    {
      trigger,
      children,
      open,
      defaultOpen = false,
      onOpenChange,
      className,
      ...otherProps
    }: AccordionRootProps,
    ref
  ) {
    return (
      <RadixCollapsible.Root
        open={open}
        defaultOpen={defaultOpen}
        onOpenChange={onOpenChange}
      >
        <div
          className={cn(
            "group/d2e81e20 flex w-full flex-col items-start rounded-md",
            className
          )}
          ref={ref}
          data-state={open ? 'open' : 'closed'}
          {...otherProps}
        >
          <Trigger>
            {trigger ? (
              <div className="flex w-full grow shrink-0 basis-0 flex-col items-start group-data-[state=open]/d2e81e20:h-auto group-data-[state=open]/d2e81e20:w-full group-data-[state=open]/d2e81e20:flex-none">
                {trigger}
              </div>
            ) : null}
          </Trigger>
          <Content>
            {children ? (
              <div className="flex w-full grow shrink-0 basis-0 flex-col items-start">
                {children}
              </div>
            ) : null}
          </Content>
        </div>
      </RadixCollapsible.Root>
    );
  }
);

export const Accordion = Object.assign(AccordionRoot, {
  Chevron,
  Content,
  Trigger,
});
