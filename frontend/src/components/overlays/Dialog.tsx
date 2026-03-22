"use client";
/**
 * Dialog Component
 * 
 * A modal dialog built on Radix UI primitives with proper z-index layering.
 * Provides a portal container context so portaled components inside (Select, etc.)
 * render within the modal and respect its stacking context.
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
        "flex min-w-[320px] flex-col items-start gap-2 rounded-md border border-solid border-neutral-border bg-default-background shadow-lg max-h-[90vh] overflow-auto",
        className
      )}
      ref={ref}
      {...otherProps}
    >
      {children}
    </div>
  ) : null;
});

interface DialogRootProps {
  children?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  /** Optional: Modal mode (default: true). When true, interaction with outside elements is disabled */
  modal?: boolean;
}

const DialogRoot = React.forwardRef<HTMLDivElement, DialogRootProps>(
  function DialogRoot(
    { children, className, open, onOpenChange, modal = true, ...otherProps }: DialogRootProps,
    ref
  ) {
    // Keep portaled children inside the dialog content's focus scope.
    const [portalContainer, setPortalContainer] = useState<HTMLElement | null>(null);

    const contentRef = useCallback((node: HTMLDivElement | null) => {
      setPortalContainer(node);

      if (typeof ref === "function") {
        ref(node);
      } else if (ref) {
        ref.current = node;
      }
    }, []);

    return (
      <RadixDialog.Root open={open} onOpenChange={onOpenChange} modal={modal}>
        <RadixDialog.Portal>
          <RadixDialog.Overlay asChild>
            <div
              className={cn(
                "fixed inset-0 z-[var(--z-modal-backdrop)] flex h-full w-full flex-col items-center justify-center gap-2 bg-[#00000099]",
                // Animate overlay
                "data-[state=open]:animate-in data-[state=closed]:animate-out",
                "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                className
              )}
              {...otherProps}
            >
              <RadixDialog.Content asChild>
                <div
                  className={cn(
                    "z-[var(--z-modal)]",
                    // Animate content
                    "data-[state=open]:animate-in data-[state=closed]:animate-out",
                    "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
                    "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
                  )}
                  ref={contentRef}
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

// Export Dialog.Close for convenience
const Close = RadixDialog.Close;

// Export Dialog.Trigger for convenience
const Trigger = RadixDialog.Trigger;

// Export Dialog.Title for accessibility
const Title = RadixDialog.Title;

// Export Dialog.Description for accessibility
const Description = RadixDialog.Description;

export const Dialog = Object.assign(DialogRoot, {
  Content,
  Close,
  Trigger,
  Title,
  Description,
});
