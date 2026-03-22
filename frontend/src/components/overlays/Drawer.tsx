"use client";
/**
 * Drawer Component
 * 
 * A side drawer built on Radix Dialog primitives.
 * Uses PortalContainerContext for proper z-index layering.
 */

import React, { useState, useCallback } from "react";
import * as RadixDialog from "@radix-ui/react-dialog";
import { cn } from "@/utils/cn";
import { PortalContainerProvider } from "@/contexts/PortalContainerContext";

interface ContentProps extends React.HTMLAttributes<HTMLDivElement> {
  children?: React.ReactNode;
  className?: string;
}

const Content = React.forwardRef<HTMLDivElement, ContentProps>(function Content(
  { children, className, ...otherProps }: ContentProps,
  ref
) {
  return children ? (
    <div
      className={cn(
        "flex h-full min-w-[320px] flex-col items-start gap-2 border-l border-solid border-neutral-border bg-default-background",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </div>
  ) : null;
});

interface DrawerRootProps {
  children?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  /** Optional: Modal mode (default: true). When true, interaction with outside elements is disabled */
  modal?: boolean;
}

const DrawerRoot = React.forwardRef<HTMLDivElement, DrawerRootProps>(
  function DrawerRoot(
    { children, className, open, onOpenChange, modal = true, ...otherProps }: DrawerRootProps,
    ref
  ) {
    // Create a ref for the portal container (the overlay element)
    const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(null);

    // Callback ref to capture the overlay element for portal container
    const overlayRef = useCallback((node: HTMLDivElement | null) => {
      setPortalContainer(node);
    }, []);

    return (
      <RadixDialog.Root open={open} onOpenChange={onOpenChange} modal={modal}>
        <RadixDialog.Portal>
          <RadixDialog.Overlay asChild>
            <div
              className={cn(
                "fixed inset-0 z-[var(--z-modal-backdrop)] flex h-full w-full flex-col items-end justify-center gap-2 bg-[#00000066]",
                // Animate overlay
                "data-[state=open]:animate-in data-[state=closed]:animate-out",
                "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                className
              )}
              ref={overlayRef}
              {...otherProps}
            >
              <RadixDialog.Content asChild>
                <div
                  className={cn(
                    "h-full z-[var(--z-modal)]",
                    // Animate content - slide in from right
                    "data-[state=open]:animate-in data-[state=closed]:animate-out",
                    "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                    "data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right"
                  )}
                  ref={ref}
                >
                  <PortalContainerProvider container={portalContainer}>
                    {children}
                  </PortalContainerProvider>
                </div>
              </RadixDialog.Content>
            </div>
          </RadixDialog.Overlay>
        </RadixDialog.Portal>
      </RadixDialog.Root>
    );
  }
);

// Export Radix primitives for convenience
const Close = RadixDialog.Close;
const Trigger = RadixDialog.Trigger;
const Title = RadixDialog.Title;
const Description = RadixDialog.Description;

export const Drawer = Object.assign(DrawerRoot, {
  Content,
  Close,
  Trigger,
  Title,
  Description,
});
